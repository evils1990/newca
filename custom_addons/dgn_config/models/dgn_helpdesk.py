# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import UserError
from dateutil import relativedelta


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"

    user_id = fields.Many2one('res.users', string='Team Lead')


class DgnHelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    source_doc = fields.Char(string='Source document')
    partner_addr = fields.Char(string='Customer Address')
    partner_phone = fields.Char(string='Customer Phone')
    total_ex_time = fields.Char(string='Total Execute Time')
    expect_date = fields.Date(string='Expect Date')
    sale_team = fields.Many2one('crm.team', 'Sales Team', oldname='section_id')
    warning_date = fields.Datetime(string='Warning Date', compute='_compute_sla')

    @api.depends('deadline', 'stage_id')
    def _compute_sla_fail(self):
        if not self.user_has_groups("helpdesk.group_use_sla"):
            return
        for ticket in self:
            ticket.sla_active = True
            if not ticket.deadline:
                ticket.sla_active = False
            elif ticket.sla_id.stage_id.sequence > ticket.stage_id.sequence:
                ticket.sla_active = False
                if datetime.utcnow() > datetime.strptime(ticket.deadline, DEFAULT_SERVER_DATETIME_FORMAT):
                    ticket.sla_fail = True

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.partner_name = self.partner_id.name
            self.partner_email = self.partner_id.email
            self.partner_addr = ('%s %s %s %s') % (self.partner_id.street or '', self.partner_id.street2 or '',
                                                  self.partner_id.city or '', self.partner_id.state_id.name or '')
            self.partner_phone = self.partner_id.phone

    @api.multi
    def write(self, vals):
        res = super(DgnHelpdeskTicket, self).write(vals)
        if vals.get('stage_id'):
            stage = self.env['helpdesk.stage'].search([('id', '=', vals.get('stage_id'))])
            if stage.is_close is True:
                datetime_now = datetime.strftime(datetime.utcnow(), '%Y-%m-%d %H:%M:%S')
                total_ex_time = datetime.strptime(datetime_now, '%Y-%m-%d %H:%M:%S') - datetime.strptime(self.create_date, '%Y-%m-%d %H:%M:%S')
                self.write({'total_ex_time': total_ex_time})
        if vals.get('user_id'):
            if self.env.user.id == self.team_id.user_id.id or self.env.user.id == 1:
                pass
            else:
                raise UserError(_('You can not edit assign field! Please contact your system administrator.'))
        return res

    @api.multi
    def assign_ticket_to_self_custom(self):
        self.ensure_one()
        if not self.user_id:
            self.user_id = self.env.user
        else:
            raise UserError(_('You can not assign yourself! The ticket has assigned.'))

    @api.depends('team_id', 'priority', 'ticket_type_id', 'create_date', 'expect_date')
    def _compute_sla(self):
        if not self.user_has_groups("helpdesk.group_use_sla"):
            return
        for ticket in self:
            dom = [('team_id', '=', ticket.team_id.id), ('priority', '<=', ticket.priority), '|',
                   ('ticket_type_id', '=', ticket.ticket_type_id.id), ('ticket_type_id', '=', False)]
            sla = ticket.env['helpdesk.sla'].search(dom, order="time_days, time_hours, time_minutes", limit=1)
            if sla and ticket.active and ticket.expect_date and ticket.create_date:
                ticket.sla_id = sla.id
                ticket.sla_name = sla.name
                ticket.deadline = fields.Datetime.from_string(ticket.expect_date) + relativedelta.relativedelta(
                    days=sla.time_days, hours=sla.time_hours, minutes=sla.time_minutes)
                if sla.w_time_days or sla.w_time_hours or sla.w_time_minutes:
                    ticket.warning_date = fields.Datetime.from_string(ticket.expect_date) + relativedelta.relativedelta(
                        days=sla.w_time_days, hours=sla.w_time_hours, minutes=sla.w_time_minutes)
            elif sla and ticket.active and ticket.create_date:
                ticket.sla_id = sla.id
                ticket.sla_name = sla.name
                ticket.deadline = fields.Datetime.from_string(ticket.create_date) + relativedelta.relativedelta(
                    days=sla.time_days, hours=sla.time_hours, minutes=sla.time_minutes)
                if sla.w_time_days or sla.w_time_hours or sla.w_time_minutes:
                    ticket.warning_date = fields.Datetime.from_string(ticket.create_date) + relativedelta.relativedelta(
                        days=sla.w_time_days, hours=sla.w_time_hours, minutes=sla.w_time_minutes)

    @api.multi
    def _change_ticket_color(self):
        tickets = self.env['helpdesk.ticket'].search([])
        today = datetime.now()

        for ticket in tickets:
            if not ticket.close_date:
                if ticket.warning_date:
                    warning_date = fields.Datetime.from_string(ticket.warning_date)
                    if today >= warning_date:
                        ticket.write({'color': 11})

                if ticket.deadline:
                    deadline_date = fields.Datetime.from_string(ticket.deadline)
                    if today >= deadline_date:
                        ticket.write({'color': 12})

class DGNHelpdeskSLA(models.Model):
    _inherit = "helpdesk.sla"

    w_time_days = fields.Integer('Days', default=0, required=True,
                                 help="Days to warning based on ticket creation date")
    w_time_hours = fields.Integer('Hours', default=0, required=True,
                                  help="Hours to warning based on ticket creation date")
    w_time_minutes = fields.Integer('Minutes', default=0, required=True,
                                    help="Minutes to warning based on ticket creation date")

    @api.onchange('w_time_hours')
    def _onchange_w_time_hours(self):
        if self.w_time_hours >= 24:
            self.w_time_days += self.w_time_hours / 24
            self.w_time_hours = self.w_time_hours % 24

    @api.onchange('w_time_minutes')
    def _onchange_w_time_minutes(self):
        if self.w_time_minutes >= 60:
            self.w_time_hours += self.w_time_minutes / 60
            self.w_time_minutes = self.w_time_minutes % 60

    @api.one
    @api.constrains('w_time_minutes', 'w_time_hours', 'w_time_days', 'time_minutes', 'time_hours', 'time_days')
    def _check_time(self):
        r_time = 24 * 60 * self.time_days + 60 * self.time_hours + self.time_minutes
        w_time = 24 * 60 * self.w_time_days + 60 * self.w_time_hours + self.w_time_minutes
        if r_time < w_time:
            raise UserError(_("Reach time must be greater than warning time."))

