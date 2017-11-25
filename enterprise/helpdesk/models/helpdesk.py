# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime

from dateutil import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError, ValidationError


TICKET_PRIORITY = [
    ('0', 'All'),
    ('1', 'Low priority'),
    ('2', 'High priority'),
    ('3', 'Urgent'),
]


class HelpdeskTeam(models.Model):
    _name = "helpdesk.team"
    _inherit = ['mail.alias.mixin', 'mail.thread', 'ir.needaction_mixin']
    _description = "Helpdesk Team"
    _order = 'sequence,name'

    name = fields.Char('Helpdesk Team', required=True, translate=True)
    description = fields.Text('About Team', translate=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env['res.company']._company_default_get('helpdesk.team'))
    sequence = fields.Integer(default=10)
    color = fields.Integer('Color Index')
    stage_ids = fields.Many2many(
        'helpdesk.stage', relation='team_stage_rel', string='Stages',
        default=[(0, 0, {'name': 'New', 'sequence': 0})],
        help="Stages the team will use. This team's tickets will only be able to be in these stages.")
    assign_method = fields.Selection([
        ('manual', 'Manually'),
        ('randomly', 'Randomly'),
        ('balanced', 'Balanced')], string='Assignation Method',
        default='manual', required=True,
        help='Automatic assignation method for new tickets:\n'
             '\tManually: manual\n'
             '\tRandomly: randomly but everyone gets the same amount\n'
             '\tBalanced: to the person with the least amount of open tickets')
    member_ids = fields.Many2many('res.users', string='Team Members', domain=lambda self: [('groups_id', 'in', self.env.ref('helpdesk.group_helpdesk_user').id)])
    ticket_ids = fields.One2many('helpdesk.ticket', 'team_id', string='Tickets')

    use_alias = fields.Boolean('Email alias')
    use_website_helpdesk_form = fields.Boolean('Website Form')
    use_website_helpdesk_livechat = fields.Boolean('Live chat',
        help="In Channel: You can create a new ticket by typing /helpdesk [ticket title]. You can search ticket by typing /helpdesk_search [Keyword1],[Keyword2],.")
    use_website_helpdesk_forum = fields.Boolean('Help Center')
    use_website_helpdesk_slides = fields.Boolean('eLearning')
    use_website_helpdesk_rating = fields.Boolean('Website Rating')
    use_twitter = fields.Boolean('Twitter')
    use_api = fields.Boolean('API')
    use_rating = fields.Boolean('Ratings')
    use_sla = fields.Boolean('SLA Policies')
    upcoming_sla_fail_tickets = fields.Integer(string='Upcoming SLA Fail Tickets', compute='_compute_upcoming_sla_fail_tickets')
    unassigned_tickets = fields.Integer(string='Unassigned Tickets', compute='_compute_unassigned_tickets')
    percentage_satisfaction = fields.Integer(
        compute="_compute_percentage_satisfaction", string="% Happy", store=True, default=-1)

    @api.depends('ticket_ids.rating_ids.rating')
    def _compute_percentage_satisfaction(self):
        for team in self:
            activities = team.ticket_ids.rating_get_grades()
            total_activity_values = sum(activities.values())
            team.percentage_satisfaction = activities['great'] * 100 / total_activity_values if total_activity_values else -1

    @api.multi
    def _compute_upcoming_sla_fail_tickets(self):
        ticket_data = self.env['helpdesk.ticket'].read_group([
            ('sla_active', '=', True),
            ('team_id', 'in', self.ids),
            ('deadline', '!=', False),
            ('deadline', '<=', fields.Datetime.to_string((datetime.date.today() + relativedelta.relativedelta(days=1)))),
        ], ['team_id'], ['team_id'])
        mapped_data = dict((data['team_id'][0], data['team_id_count']) for data in ticket_data)
        for team in self:
            team.upcoming_sla_fail_tickets = mapped_data.get(team.id, 0)

    @api.multi
    def _compute_unassigned_tickets(self):
        ticket_data = self.env['helpdesk.ticket'].read_group([('user_id', '=', False), ('team_id', 'in', self.ids), ('stage_id.is_close', '!=', True)], ['team_id'], ['team_id'])
        mapped_data = dict((data['team_id'][0], data['team_id_count']) for data in ticket_data)
        for team in self:
            team.unassigned_tickets = mapped_data.get(team.id, 0)

    @api.onchange('member_ids')
    def _onchange_member_ids(self):
        if not self.member_ids:
            self.assign_method = 'manual'

    @api.constrains('assign_method', 'member_ids')
    def _check_member_assignation(self):
        if not self.member_ids and self.assign_method != 'manual':
            raise ValidationError(_("You must have team members assigned to change the assignation method."))

    @api.onchange('use_alias')
    def _onchange_use_alias(self):
        if not self.alias_name:
            self.alias_name = self.env['mail.alias']._clean_and_make_unique(self.name) if self.use_alias else False

    @api.model
    def create(self, vals):
        team = super(HelpdeskTeam, self.with_context(mail_create_nolog=True, mail_create_nosubscribe=True)).create(vals)
        team.sudo()._check_sla_group()
        team.sudo()._check_modules_to_install()
        # If you plan to add something after this, use a new environment. The one above is no longer valid after the modules install.
        return team

    @api.multi
    def write(self, vals):
        result = super(HelpdeskTeam, self).write(vals)
        self.sudo()._check_sla_group()
        self.sudo()._check_modules_to_install()
        # If you plan to add something after this, use a new environment. The one above is no longer valid after the modules install.
        return result

    @api.multi
    def unlink(self):
        stages = self.mapped('stage_ids').filtered(lambda stage: stage.team_ids <= self)
        stages.unlink()
        return super(HelpdeskTeam, self).unlink()

    @api.multi
    def _check_sla_group(self):
        for team in self:
            if team.use_sla and not self.user_has_groups('helpdesk.group_use_sla'):
                self.env.ref('helpdesk.group_helpdesk_user').write({'implied_ids': [(4, self.env.ref('helpdesk.group_use_sla').id)]})
            if team.use_sla:
                self.env['helpdesk.sla'].with_context(active_test=False).search([('team_id', '=', team.id), ('active', '=', False)]).write({'active': True})
            else:
                self.env['helpdesk.sla'].search([('team_id', '=', team.id)]).write({'active': False})
                if not self.search_count([('use_sla', '=', True)]):
                    self.env.ref('helpdesk.group_helpdesk_user').write({'implied_ids': [(3, self.env.ref('helpdesk.group_use_sla').id)]})
                    self.env.ref('helpdesk.group_use_sla').write({'users': [(5, 0, 0)]})

    @api.multi
    def _check_modules_to_install(self):
        module_installed = False
        for team in self:
            form_module = self.env['ir.module.module'].search([('name', '=', 'website_helpdesk_form')])
            if self.use_website_helpdesk_form and form_module.state not in ('installed', 'to install', 'to upgrade'):
                form_module.button_immediate_install()
                module_installed = True

            livechat_module = self.env['ir.module.module'].search([('name', '=', 'website_helpdesk_livechat')])
            if self.use_website_helpdesk_livechat and livechat_module.state not in ('installed', 'to install', 'to upgrade'):
                livechat_module.button_immediate_install()
                module_installed = True

            forum_module = self.env['ir.module.module'].search([('name', '=', 'website_helpdesk_forum')])
            if self.use_website_helpdesk_forum and forum_module.state not in ('installed', 'to install', 'to upgrade'):
                forum_module.button_immediate_install()
                module_installed = True

            slides_module = self.env['ir.module.module'].search([('name', '=', 'website_helpdesk_slides')])
            if self.use_website_helpdesk_slides and slides_module.state not in ('installed', 'to install', 'to upgrade'):
                slides_module.button_immediate_install()
                module_installed = True

            rating_module = self.env['ir.module.module'].search([('name', '=', 'website_helpdesk')])
            if self.use_website_helpdesk_rating and rating_module.state not in ('installed', 'to install', 'to upgrade'):
                rating_module.button_immediate_install()
                module_installed = True
        # just in case we want to do something if we install a module. (like a refresh ...)
        return module_installed

    def get_alias_model_name(self, vals):
        return vals.get('alias_model', 'helpdesk.ticket')

    def get_alias_values(self):
        values = super(HelpdeskTeam, self).get_alias_values()
        values['alias_defaults'] = {'team_id': self.id}
        return values

    @api.model
    def retrieve_dashboard(self):
        domain = [('user_id', '=', self.env.uid)]
        group_fields = ['priority', 'create_date', 'stage_id', 'close_hours']
        #TODO: remove SLA calculations if user_uses_sla is false.
        user_uses_sla = self.user_has_groups('helpdesk.group_use_sla') and\
            bool(self.env['helpdesk.team'].search([('use_sla', '=', True), '|', ('member_ids', 'in', self._uid), ('member_ids', '=', False)]))
        if user_uses_sla:
            group_fields.insert(1, 'sla_fail')
        HelpdeskTicket = self.env['helpdesk.ticket']
        tickets = HelpdeskTicket.read_group(domain + [('stage_id.is_close', '=', False)], group_fields, group_fields, lazy=False)
        result = {
            'helpdesk_target_closed': self.env.user.helpdesk_target_closed,
            'helpdesk_target_rating': self.env.user.helpdesk_target_rating,
            'helpdesk_target_success': self.env.user.helpdesk_target_success,
            'today': {'count': 0, 'rating': 0, 'success': 0},
            '7days': {'count': 0, 'rating': 0, 'success': 0},
            'my_all': {'count': 0, 'hours': 0, 'failed': 0},
            'my_high': {'count': 0, 'hours': 0, 'failed': 0},
            'my_urgent': {'count': 0, 'hours': 0, 'failed': 0},
            'show_demo': not bool(HelpdeskTicket.search([], limit=1)),
            'rating_enable': False,
            'success_rate_enable': user_uses_sla
        }

        def add_to(ticket, key="my_all"):
            result[key]['count'] += ticket['__count']
            result[key]['hours'] += ticket['close_hours']
            if ticket.get('sla_fail'):
                result[key]['failed'] += ticket['__count']

        for ticket in tickets:
            add_to(ticket, 'my_all')
            if ticket['priority'] in ('2'):
                add_to(ticket, 'my_high')
            if ticket['priority'] in ('3'):
                add_to(ticket, 'my_urgent')

        dt = fields.Date.today()
        tickets = HelpdeskTicket.read_group(domain + [('stage_id.is_close', '=', True), ('close_date', '>=', dt)], group_fields, group_fields, lazy=False)
        for ticket in tickets:
            result['today']['count'] += ticket['__count']
            if not ticket.get('sla_fail'):
                result['today']['success'] += ticket['__count']

        dt = fields.Datetime.to_string((datetime.date.today() - relativedelta.relativedelta(days=6)))
        tickets = HelpdeskTicket.read_group(domain + [('stage_id.is_close', '=', True), ('close_date', '>=', dt)], group_fields, group_fields, lazy=False)
        for ticket in tickets:
            result['7days']['count'] += ticket['__count']
            if not ticket.get('sla_fail'):
                result['7days']['success'] += ticket['__count']

        result['today']['success'] = (result['today']['success'] * 100) / (result['today']['count'] or 1)
        result['7days']['success'] = (result['7days']['success'] * 100) / (result['7days']['count'] or 1)
        result['my_all']['hours'] = result['my_all']['hours'] / (result['my_all']['count'] or 1)
        result['my_high']['hours'] = result['my_high']['hours'] / (result['my_high']['count'] or 1)
        result['my_urgent']['hours'] = result['my_urgent']['hours'] / (result['my_urgent']['count'] or 1)

        if self.env['helpdesk.team'].search([('use_rating', '=', True), '|', ('member_ids', 'in', self._uid), ('member_ids', '=', False)]):
            result['rating_enable'] = True
            # rating of today
            domain = [('user_id', '=', self.env.uid)]
            dt = fields.Date.today()
            tickets = self.env['helpdesk.ticket'].search(domain + [('stage_id.is_close', '=', True), ('close_date', '>=', dt)])
            activity = tickets.rating_get_grades()
            total_rating = self.compute_activity_avg(activity)
            total_activity_values = sum(activity.values())
            team_satisfaction = round((total_rating / total_activity_values if total_activity_values else 0), 2)
            if team_satisfaction:
                result['today']['rating'] = team_satisfaction

            # rating of last 7 days (6 days + today)
            dt = fields.Datetime.to_string((datetime.date.today() - relativedelta.relativedelta(days=6)))
            tickets = self.env['helpdesk.ticket'].search(domain + [('stage_id.is_close', '=', True), ('close_date', '>=', dt)])
            activity = tickets.rating_get_grades()
            total_rating = self.compute_activity_avg(activity)
            total_activity_values = sum(activity.values())
            team_satisfaction_7days = round((total_rating / total_activity_values if total_activity_values else 0), 2)
            if team_satisfaction_7days:
                result['7days']['rating'] = team_satisfaction_7days
        return result

    @api.multi
    def action_view_ticket_rating(self):
        """ return the action to see all the rating about the tickets of the Team """
        domain = [('team_id', 'in', self.ids)]
        if self.env.context.get('seven_days'):
            domain += [('close_date', '>=', fields.Datetime.to_string((datetime.date.today() - relativedelta.relativedelta(days=6))))]
        elif self.env.context.get('today'):
            domain += [('close_date', '>=', fields.Datetime.to_string(datetime.date.today()))]
        if self.env.context.get('helpdesk'):
            domain += [('user_id', '=', self._uid), ('stage_id.is_close', '=', True)]
        ticket_ids = self.env['helpdesk.ticket'].search(domain).ids
        domain = [('res_id', 'in', ticket_ids), ('rating', '!=', -1), ('res_model', '=', 'helpdesk.ticket')]
        action = self.env.ref('rating.action_view_rating').read()[0]
        action['domain'] = domain
        return action

    @api.model
    def helpdesk_rating_today(self):
        #  call this method of on click "Customer Rating" button on dashbord for today rating of teams tickets
        return self.search(['|', ('member_ids', 'in', self._uid), ('member_ids', '=', False)]).with_context(helpdesk=True, today=True).action_view_ticket_rating()

    @api.model
    def helpdesk_rating_7days(self):
        #  call this method of on click "Customer Rating" button on dashbord for last 7days rating of teams tickets
        return self.search(['|', ('member_ids', 'in', self._uid), ('member_ids', '=', False)]).with_context(helpdesk=True, seven_days=True).action_view_ticket_rating()

    @api.multi
    def action_view_all_rating(self):
        """ return the action to see all the rating about the all sort of activity of the team (tickets) """
        return self.action_view_ticket_rating()

    @api.multi
    def action_unhappy_rating_ticket(self):
        self.ensure_one()
        action = self.env.ref('helpdesk.helpdesk_ticket_action_main').read()[0]
        action['domain'] = [('team_id', '=', self.id), ('user_id', '=', self.env.uid), ('rating_ids.rating', '=', 1)]
        action['context'] = {'default_team_id': self.id}
        return action

    @api.model
    def compute_activity_avg(self, activity):
        # compute average base on all rating value
        # like: 5 great, 2 okey, 1 bad
        # great = 10, okey = 5, bad = 0
        # (5*10) + (2*5) + (1*0) = 60 / 8 (nuber of activity for rating)
        great = activity['great'] * 10.00
        okey = activity['okay'] * 5.00
        bad = activity['bad'] * 0.00
        return great + okey + bad

    @api.model
    def modify_target_helpdesk_team_dashboard(self, target_name, target_value):
        if target_name:
            self.env.user.sudo().write({target_name: target_value})
        else:
            raise UserError(_('This target does not exist.'))

    @api.multi
    def get_new_user(self):
        self.ensure_one()
        new_user = self.env['res.users']
        member_ids = sorted(self.member_ids.ids)
        if member_ids:
            if self.assign_method == 'randomly':
                # randomly means new ticketss get uniformly distributed
                previous_assigned_user = self.env['helpdesk.ticket'].search([('team_id', '=', self.id)], order='create_date desc', limit=1).user_id
                # handle the case where the previous_assigned_user has left the team (or there is none).
                if previous_assigned_user and previous_assigned_user.id in member_ids:
                    previous_index = member_ids.index(previous_assigned_user.id)
                    new_user = new_user.browse(member_ids[(previous_index + 1) % len(member_ids)])
                else:
                    new_user = new_user.browse(member_ids[0])
            elif self.assign_method == 'balanced':
                read_group_res = self.env['helpdesk.ticket'].read_group([('stage_id.is_close', '=', False), ('user_id', 'in', member_ids)], ['user_id'], ['user_id'])
                # add all the members in case a member has no more open tickets (and thus doesn't appear in the previous read_group)
                count_dict = dict((m_id, 0) for m_id in member_ids)
                count_dict.update((data['user_id'][0], data['user_id_count']) for data in read_group_res)
                new_user = new_user.browse(min(count_dict, key=count_dict.get))
        return new_user


class HelpdeskStage(models.Model):
    _name = 'helpdesk.stage'
    _description = 'Stage'
    _order = 'sequence, id'

    def _get_default_team_ids(self):
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return [(4, team_id, 0)]

    name = fields.Char(required=True)
    sequence = fields.Integer('Sequence', default=10)
    is_close = fields.Boolean(
        'Closing Kanban Stage',
        help='Tickets in this stage are considered as done. This is used notably when '
             'computing SLAs and KPIs on tickets.')
    fold = fields.Boolean(
        'Folded', help='Folded in kanban view')
    team_ids = fields.Many2many(
        'helpdesk.team', relation='team_stage_rel', string='Team',
        default=_get_default_team_ids,
        help='Specific team that uses this stage. Other teams will not be able to see or use this stage.')
    template_id = fields.Many2one(
        'mail.template', 'Automated Answer Email Template',
        domain="[('model', '=', 'helpdesk.ticket')]",
        help="Automated email sent to the ticket's customer when the ticket reaches this stage.")


class HelpdeskTicketType(models.Model):
    _name = 'helpdesk.ticket.type'
    _description = 'Ticket Type'
    _order = 'sequence'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', _("Type name already exists !")),
    ]


class HelpdeskTag(models.Model):
    _name = 'helpdesk.tag'
    _description = 'Tags'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer('Color')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', _("Tag name already exists !")),
    ]


class HelpdeskSLA(models.Model):
    _name = "helpdesk.sla"
    _order = "name"
    _description = "Helpdesk SLA Policies"

    name = fields.Char('SLA Policy Name', required=True, index=True)
    description = fields.Text('SLA Policy Description')
    active = fields.Boolean('Active', default=True)
    team_id = fields.Many2one('helpdesk.team', 'Team', required=True)
    ticket_type_id = fields.Many2one(
        'helpdesk.ticket.type', "Ticket Type",
        help="Only apply the SLA to a specific ticket type. If left empty it will apply to all types.")
    stage_id = fields.Many2one(
        'helpdesk.stage', 'Target Stage', required=True,
        help='Minimum stage a ticket needs to reach in order to satisfy this SLA.')
    priority = fields.Selection(
        TICKET_PRIORITY, string='Minimum Priority',
        default='0', required=True,
        help='Tickets under this priority will not be taken into account.')
    company_id = fields.Many2one('res.company', 'Company', related='team_id.company_id', readonly=True, store=True)
    time_days = fields.Integer('Days', default=0, required=True, help="Days to reach given stage based on ticket creation date")
    time_hours = fields.Integer('Hours', default=0, required=True, help="Hours to reach given stage based on ticket creation date")
    time_minutes = fields.Integer('Minutes', default=0, required=True, help="Minutes to reach given stage based on ticket creation date")

    @api.onchange('time_hours')
    def _onchange_time_hours(self):
        if self.time_hours >= 24:
            self.time_days += self.time_hours / 24
            self.time_hours = self.time_hours % 24

    @api.onchange('time_minutes')
    def _onchange_time_minutes(self):
        if self.time_minutes >= 60:
            self.time_hours += self.time_minutes / 60
            self.time_minutes = self.time_minutes % 60


class HelpdeskTicket(models.Model):
    _name = 'helpdesk.ticket'
    _description = 'Ticket'
    _order = 'priority desc, id desc'
    _inherit = ['mail.thread', 'ir.needaction_mixin', 'utm.mixin', 'rating.mixin']

    @api.model
    def default_get(self, fields):
        res = super(HelpdeskTicket, self).default_get(fields)
        if res.get('team_id'):
            update_vals = self._onchange_team_get_values(self.env['helpdesk.team'].browse(res['team_id']))
            if (not fields or 'user_id' in fields) and 'user_id' not in res:
                res['user_id'] = update_vals['user_id']
            if (not fields or 'stage_id' in fields) and 'stage_id' not in res:
                res['stage_id'] = update_vals['stage_id']
        return res

    def _default_team_id(self):
        team_id = self._context.get('default_team_id')
        if not team_id:
            team_id = self.env['helpdesk.team'].search([('member_ids', 'in', self.env.uid)], limit=1).id
        if not team_id:
            team_id = self.env['helpdesk.team'].search([], limit=1).id
        return team_id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        # write the domain
        # - ('id', 'in', stages.ids): add columns that should be present
        # - OR ('team_ids', '=', team_id) if team_id: add team columns
        search_domain = [('id', 'in', stages.ids)]
        if self.env.context.get('default_team_id'):
            search_domain = ['|', ('team_ids', 'in', self.env.context['default_team_id'])] + search_domain

        return stages.search(search_domain, order=order)

    name = fields.Char(string='Subject', required=True, index=True)

    team_id = fields.Many2one('helpdesk.team', string='Helpdesk Team', default=_default_team_id, index=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    ticket_type_id = fields.Many2one('helpdesk.ticket.type', string="Ticket Type")
    tag_ids = fields.Many2many('helpdesk.tag', string='Tags')
    company_id = fields.Many2one(related='team_id.company_id', string='Company', store=True, readonly=True)
    color = fields.Integer(string='Color Index')
    kanban_state = fields.Selection([
        ('normal', 'Normal'),
        ('blocked', 'Blocked'),
        ('done', 'Ready for next stage')], string='Kanban State',
        default='normal', required=True, track_visibility='onchange',
        help="A ticket's kanban state indicates special situations affecting it:\n"
             "* Normal is the default situation\n"
             "* Blocked indicates something is preventing the progress of this issue\n"
             "* Ready for next stage indicates the issue is ready to be pulled to the next stage")
    user_id = fields.Many2one('res.users', string='Assigned to', track_visibility='onchange', domain=lambda self: [('groups_id', 'in', self.env.ref('helpdesk.group_helpdesk_user').id)])
    partner_id = fields.Many2one('res.partner', string='Customer')
    partner_tickets = fields.Integer('Number of tickets from the same partner', compute='_compute_partner_tickets')

    # Used to submit tickets from a contact form
    partner_name = fields.Char(string='Customer Name')
    partner_email = fields.Char(string='Customer Email')

    priority = fields.Selection(TICKET_PRIORITY, string='Priority', default='0')
    stage_id = fields.Many2one('helpdesk.stage', string='Stage', track_visibility='onchange',
                               group_expand='_read_group_stage_ids', copy=False,
                               index=True, domain="[('team_ids', '=', team_id)]")

    # next 4 fields are computed in write (or create)
    assign_date = fields.Datetime(string='First assignation date')
    assign_hours = fields.Integer(string='Time to first assignation (hours)', compute='_compute_assign_hours', store=True)
    close_date = fields.Datetime(string='Close date')
    close_hours = fields.Integer(string='Open Time (hours)', compute='_compute_close_hours', store=True)

    sla_id = fields.Many2one('helpdesk.sla', string='SLA Policy', compute='_compute_sla', store=True)
    sla_name = fields.Char(string='SLA Policy name', compute='_compute_sla', store=True)  # care if related -> crash on creation with a team.
    deadline = fields.Datetime(string='Deadline', compute='_compute_sla', store=True)
    sla_active = fields.Boolean(string='SLA active', compute='_compute_sla_fail', store=True)
    sla_fail = fields.Boolean(string='Failed SLA Policy', compute='_compute_sla_fail', store=True)

    def _onchange_team_get_values(self, team):
        return {
            'user_id': team.get_new_user().id,
            'stage_id': self.env['helpdesk.stage'].search([('team_ids', 'in', team.id)], order='sequence', limit=1).id
        }

    @api.onchange('team_id')
    def _onchange_team_id(self):
        if self.team_id:
            update_vals = self._onchange_team_get_values(self.team_id)
            if not self.user_id:
                self.user_id = update_vals['user_id']
            if not self.stage_id or self.stage_id not in self.team_id.stage_ids:
                self.stage_id = update_vals['stage_id']

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.partner_name = self.partner_id.name
            self.partner_email = self.partner_id.email

    @api.depends('partner_id')
    def _compute_partner_tickets(self):
        self.ensure_one()
        ticket_data = self.env['helpdesk.ticket'].read_group([
            ('partner_id', '=', self.partner_id.id),
            ('stage_id.is_close', '=', False)
        ], ['partner_id'], ['partner_id'])
        if ticket_data:
            self.partner_tickets = ticket_data[0]['partner_id_count']

    @api.depends('assign_date')
    def _compute_assign_hours(self):
        for ticket in self:
            time_difference = datetime.datetime.now() - fields.Datetime.from_string(ticket.create_date)
            ticket.assign_hours = (time_difference.seconds) / 3600 + time_difference.days * 24

    @api.depends('close_date')
    def _compute_close_hours(self):
        for ticket in self:
            time_difference = datetime.datetime.now() - fields.Datetime.from_string(ticket.create_date)
            ticket.close_hours = (time_difference.seconds) / 3600 + time_difference.days * 24

    @api.depends('team_id', 'priority', 'ticket_type_id', 'create_date')
    def _compute_sla(self):
        if not self.user_has_groups("helpdesk.group_use_sla"):
            return
        for ticket in self:
            dom = [('team_id', '=', ticket.team_id.id), ('priority', '<=', ticket.priority), '|', ('ticket_type_id', '=', ticket.ticket_type_id.id), ('ticket_type_id', '=', False)]
            sla = ticket.env['helpdesk.sla'].search(dom, order="time_days, time_hours, time_minutes", limit=1)
            if sla and ticket.active and ticket.create_date:
                ticket.sla_id = sla.id
                ticket.sla_name = sla.name
                ticket.deadline = fields.Datetime.from_string(ticket.create_date) + relativedelta.relativedelta(days=sla.time_days, hours=sla.time_hours, minutes=sla.time_minutes)

    @api.depends('deadline', 'stage_id')
    def _compute_sla_fail(self):
        if not self.user_has_groups("helpdesk.group_use_sla"):
            return
        for ticket in self:
            ticket.sla_active = True
            if not ticket.deadline:
                ticket.sla_active = False
            elif ticket.sla_id.stage_id.sequence <= ticket.stage_id.sequence:
                ticket.sla_active = False
                if fields.Datetime.now() > ticket.deadline:
                    ticket.sla_fail = True

    @api.model
    def create(self, vals):
        if vals.get('team_id'):
            vals.update(item for item in self._onchange_team_get_values(self.env['helpdesk.team'].browse(vals['team_id'])).items() if item[0] not in vals)

        # context: no_log, because subtype already handle this
        ticket = super(HelpdeskTicket, self.with_context(mail_create_nolog=True)).create(vals)
        if ticket.partner_id:
            ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
            ticket._onchange_partner_id()
        if ticket.user_id:
            ticket.assign_date = ticket.create_date
            ticket.assign_hours = 0

        return ticket

    @api.multi
    def write(self, vals):
        # we set the assignation date (assign_date) to now for tickets that are being assigned for the first time
        # same thing for the closing date
        assigned_tickets = closed_tickets = self.browse()
        if vals.get('user_id'):
            assigned_tickets = self.filtered(lambda ticket: not ticket.assign_date)
        if vals.get('stage_id') and self.env['helpdesk.stage'].browse(vals.get('stage_id')).is_close:
            closed_tickets = self.filtered(lambda ticket: not ticket.close_date)
        now = datetime.datetime.now()
        res = super(HelpdeskTicket, self - assigned_tickets - closed_tickets).write(vals)
        res &= super(HelpdeskTicket, assigned_tickets - closed_tickets).write(dict(vals, **{
            'assign_date': now,
        }))
        res &= super(HelpdeskTicket, closed_tickets - assigned_tickets).write(dict(vals, **{
            'close_date': now,
        }))
        res &= super(HelpdeskTicket, assigned_tickets & closed_tickets).write(dict(vals, **{
            'assign_date': now,
            'close_date': now,
        }))
        if vals.get('partner_id'):
            self.message_subscribe([vals['partner_id']])

        return res

    @api.multi
    def name_get(self):
        result = []
        for ticket in self:
            result.append((ticket.id, "%s (#%d)" % (ticket.name, ticket.id)))
        return result

    # Method to called by CRON to update SLA & statistics
    @api.model
    def recompute_all(self):
        tickets = self.search([('stage_id.is_close', '=', False)])
        tickets._compute_sla()
        tickets._compute_close_hours()
        return True

    @api.multi
    def assign_ticket_to_self(self):
        self.ensure_one()
        self.user_id = self.env.user

    @api.multi
    def open_customer_tickets(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Tickets'),
            'res_model': 'helpdesk.ticket',
            'view_mode': 'kanban,tree,form,pivot,graph',
            'context': {'search_default_is_open': True, 'search_default_partner_id': self.partner_id.id}
        }

    #DVE FIXME: if partner gets created when sending the message it should be set as partner_id of the ticket.
    @api.multi
    def message_get_suggested_recipients(self):
        recipients = super(HelpdeskTicket, self).message_get_suggested_recipients()
        try:
            for ticket in self:
                if ticket.partner_id:
                    ticket._message_add_suggested_recipient(recipients, partner=ticket.partner_id, reason=_('Customer'))
                elif ticket.partner_email:
                    ticket._message_add_suggested_recipient(recipients, email=ticket.partner_email, reason=_('Customer Email'))
        except AccessError:  # no read access rights -> just ignore suggested recipients because this implies modifying followers
            pass
        return recipients

    @api.model
    def message_new(self, msg, custom_values=None):
        values = dict(custom_values or {}, partner_email=msg.get('from'), partner_id=msg.get('author_id'))
        return super(HelpdeskTicket, self).message_new(msg, custom_values=values)

    @api.multi
    def _track_template(self, tracking):
        res = super(HelpdeskTicket, self)._track_template(tracking)
        ticket = self[0]
        changes, tracking_value_ids = tracking[ticket.id]
        if 'stage_id' in changes and ticket.stage_id.template_id:
            res['stage_id'] = (ticket.stage_id.template_id, {'composition_mode': 'mass_mail', 'auto_delete_message': True})
        return res

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'user_id' in init_values and self.user_id:
            return 'helpdesk.mt_ticket_assigned'
        elif 'stage_id' in init_values and self.stage_id.sequence < 1:
            return 'helpdesk.mt_ticket_new'
        elif 'stage_id' in init_values and self.stage_id.sequence >= 1:
            return 'helpdesk.mt_ticket_stage'
        return super(HelpdeskTicket, self)._track_subtype(init_values)

    @api.multi
    def _notification_recipients(self, message, groups):
        """ Handle salesman recipients that can convert leads into opportunities
        and set opportunities as won / lost. """
        groups = super(HelpdeskTicket, self)._notification_recipients(message, groups)

        self.ensure_one()
        if not self.user_id:
            take_action = self._notification_link_helper('assign')
            helpdesk_actions = [{'url': take_action, 'title': _('I take it')}]
        else:
            new_action_id = self.env.ref('helpdesk.helpdesk_ticket_action_main').id
            new_action = self._notification_link_helper('new', action_id=new_action_id)
            helpdesk_actions = [{'url': new_action, 'title': _('New Ticket')}]

        new_group = (
            'group_helpdesk_user', lambda partner: bool(partner.user_ids) and any(user.has_group('helpdesk.group_helpdesk_user') for user in partner.user_ids), {
                'actions': helpdesk_actions,
            })

        return [new_group] + groups

    @api.model
    def message_get_reply_to(self, res_ids, default=None):
        res = {}
        for res_id in res_ids:
            if self.browse(res_id).team_id.alias_name and self.browse(res_id).team_id.alias_domain:
                res[res_id] = self.browse(res_id).team_id.alias_name + '@' + self.browse(res_id).team_id.alias_domain
            else:
                res[res_id] = super(HelpdeskTicket, self).message_get_reply_to([res_id])[res_id]
        return res
