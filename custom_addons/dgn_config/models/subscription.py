# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
import odoo.addons.decimal_precision as dp
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
import calendar

class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    date_unit_price = fields.Float('Price', digits=dp.get_precision('Product Price'), default=False)
    subscription_line_id = fields.Many2one('sale.subscription.line', string='Subscription Line')


class SaleSubscriptionTemplate(models.Model):
    _inherit = "sale.subscription.template"

    prepaid = fields.Boolean(string="Prepaid", help="If checked, subscription will be invoiced by ordered quantity (or by actual usage, if not).")


class SaleSubscription(models.Model):
    _inherit = "sale.subscription"
    recurring_invoice_line_ids = fields.One2many('sale.subscription.line', 'analytic_account_id',
                                                 string='Invoice Lines', copy=True,
                                                 domain=[('is_actual', '=', False)])
    project_line_ids = fields.One2many('sale.subscription.line', 'analytic_account_id',
                                       string='Actual Lines', copy=True,
                                       domain=[('is_actual', '=', True)])

    actual_recurring_total = fields.Float(compute='_compute_actual_recurring_total', string="Actual Amount", store=True,
                                   track_visibility='onchange')

    prepaid = fields.Boolean(related='template_id.prepaid', string='Prepaid')

    crm_team_id = fields.Many2one('crm.team', 'Sales Team')
    quote_template_id = fields.Many2one('sale.quote.template', 'Quotation Template Reference')
    is_manual_date = fields.Boolean("Setting start date for Postpaid manually?")
    start_date_fee = fields.Date(string='Actual start date')
    cancel_date = fields.Date(string='Cancel Date of Subscription')
    origin_create = fields.Selection([
        ('ts', 'ts'),
        ('st', 'st'),
        ('new', 'new'),
    ], string='Origin Create', readonly=True, copy=False, index=True,default='new')

    @api.model
    def dgn_cron_account_analytic_account(self):
        today = fields.Date.today()
        next_month = fields.Date.to_string(fields.Date.from_string(today) + relativedelta(months=1))

        # set to pending if date is in less than a month
        domain_pending = [('date', '<', next_month), ('state', '=', 'none')] #Dirty hack
        subscriptions_pending = self.search(domain_pending)
        subscriptions_pending.write({'state': 'pending'})

        # set to close if data is passed
        domain_close = [('date', '<', today), ('state', 'in', ['pending', 'open'])]
        subscriptions_close = self.search(domain_close)

        subscriptions_close.write({'state': 'close'})

        return dict(pending=subscriptions_pending.ids, closed=subscriptions_close.ids)

    @api.model
    def dgn_cron_cancel(self):
        today = fields.Date.today()

        # set to close if data is passed
        domain_close = [('cancel_date', '<', today), ('state', 'in', ['pending', 'open'])]
        subscriptions_close = self.search(domain_close)

        subscriptions_close.write({'state': 'cancel'})


    @api.depends('project_line_ids', 'project_line_ids.quantity',
                 'project_line_ids.price_subtotal')
    def _compute_actual_recurring_total(self):
        for account in self:
            account.actual_recurring_total = sum(line.price_subtotal for line in account.project_line_ids)

    @api.model
    def push_timesheet(self):
            timesheets = self.env['account.analytic.line']
            now = datetime.utcnow()
            current_date = datetime.utcnow().strftime(DEFAULT_SERVER_DATE_FORMAT)
            uom_month = self.env.ref('dgn_config.product_uom_month')
            active_ids = self.sudo().search([('state', '=', 'open')])
            uom_day = self.env.ref('product.product_uom_day')
            for contract in active_ids:
                # if contract.prepaid:
                #     continue

                try:
                    line_ids = contract.recurring_invoice_line_ids
                    for line in line_ids:
                        day_price_unit = contract.pricelist_id.with_context(uom=uom_day.id).get_product_price(line.product_id, 1, contract.partner_id, current_date, uom_day.id)
                        if line.product_id.uom_id.id == uom_month.id:
                            day_of_month = calendar.monthrange(now.year, now.month)[1]
                            day_price_unit = day_price_unit * uom_month.factor_inv / day_of_month

                        values = {
                            'name': line.product_id.name,
                            'account_id': contract.analytic_account_id.id,
                            'date': current_date,
                            'unit_amount': 8,
                            'date_unit_price': day_price_unit,
                            'subscription_line_id': line.id,
                        }
                        timesheets.sudo().create(values)
                    self.env.cr.commit()
                except Exception:
                    self.env.cr.rollback()

    @api.multi
    def _prepare_invoice(self):
        self.project_line_ids.unlink()
        return super(SaleSubscription, self)._prepare_invoice()

    @api.multi
    def _prepare_invoice_lines(self, fiscal_position):
        for subscription_line in self.recurring_invoice_line_ids:
            subscription_line.calculate_actual()
            self.write({'is_manual_date': False})
            self.write({'start_date_fee': False})


        fiscal_position = self.env['account.fiscal.position'].browse(fiscal_position)
        return [(0, 0, self._prepare_invoice_line(line, fiscal_position)) for line in self.project_line_ids]

    @api.multi
    def _prepare_invoice_data(self):
        self.ensure_one()
        res = super(SaleSubscription, self)._prepare_invoice_data()

        if not self.prepaid:
            end_date = fields.Date.from_string(self.recurring_next_date)
            periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
            next_date = self.is_manual_date and fields.Date.from_string(self.start_date_fee) or (end_date - relativedelta(**{periods[self.recurring_rule_type]: self.recurring_interval}))
            end_date = end_date - relativedelta(days=1)  # remove 1 day as normal people thinks in term of inclusive ranges.
            res['comment'] = _("This invoice covers the following period: %s - %s") % (next_date, end_date)

        return res

    @api.multi
    def dgn_set_open(self):
        periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
        current_date = datetime.utcnow() + relativedelta(**{periods[self.recurring_rule_type]: self.recurring_interval})
        current_date = current_date.strftime(DEFAULT_SERVER_DATE_FORMAT)

        if self.origin_create == 'ts':
            #set to 1st day of next month
            begin_day = datetime.strptime(self.recurring_next_date, DEFAULT_SERVER_DATE_FORMAT).date()
            first_day_of_next_week = (begin_day + timedelta(days=7)) - relativedelta(days=begin_day.weekday())
            first_day_of_next_month = (begin_day + relativedelta(months=1)).replace(day=1)
            first_day_of_next_year = (begin_day + relativedelta(years=1)).replace(day=1).replace(month=1)
            if self.recurring_rule_type == 'weekly':
                begin_day = first_day_of_next_week
            elif self.recurring_rule_type == 'monthly':
                begin_day = first_day_of_next_month
            elif self.recurring_rule_type == 'yearly':
                begin_day = first_day_of_next_year

            self.write({'recurring_next_date': begin_day})
        elif self.origin_create == 'st':
            # set to back one month
            begin_day = datetime.strptime(self.recurring_next_date, DEFAULT_SERVER_DATE_FORMAT).date()
            first_day_of_last_week = (begin_day - timedelta(days=7)) - relativedelta(days=begin_day.weekday())
            first_day_of_last_month = (begin_day - relativedelta(months=1)).replace(day=1)
            first_day_of_last_year = (begin_day - relativedelta(years=1)).replace(day=1).replace(month=1)
            if self.recurring_rule_type == 'weekly':
                begin_day = first_day_of_last_week
            elif self.recurring_rule_type == 'monthly':
                begin_day = first_day_of_last_month
            elif self.recurring_rule_type == 'yearly':
                begin_day = first_day_of_last_year

            self.write({'recurring_next_date': begin_day})
        else:
            if not self.prepaid:
                if not self.recurring_next_date:
                    self.write({'recurring_next_date': current_date})

                begin_day = datetime.strptime(self.recurring_next_date, DEFAULT_SERVER_DATE_FORMAT).date()
                first_day_of_current_week = begin_day - relativedelta(days=begin_day.weekday())
                first_day_of_current_month = begin_day.replace(day=1)
                first_day_of_current_year = begin_day.replace(day=1).replace(month=1)
                if self.recurring_rule_type == 'weekly':
                    begin_day = first_day_of_current_week
                elif self.recurring_rule_type == 'monthly':
                    begin_day = first_day_of_current_month
                elif self.recurring_rule_type == 'yearly':
                    begin_day = first_day_of_current_year

                self.write({'recurring_next_date': begin_day})

        res = super(SaleSubscription, self).set_open()
        for order in self:
            for line in order.recurring_invoice_line_ids:
                if line.service_account:
                    line.service_account.sudo().do_active()
        return res

    @api.multi
    def set_cancel(self):
        # res = super(SaleSubscription, self).set_cancel()
        for order in self:
            for line in order.recurring_invoice_line_ids:
                if line.service_account:
                    line.service_account.sudo().do_deactive()
        # return res

    @api.multi
    def set_close(self):
        # res = super(SaleSubscription, self).set_close()
        for order in self:
            for line in order.recurring_invoice_line_ids:
                if line.service_account:
                    line.service_account.sudo().do_deactive()
        # return res

    @api.multi
    def set_pending(self):
        res = super(SaleSubscription, self).set_pending()
        for order in self:
            for line in order.recurring_invoice_line_ids:
                if line.service_account:
                    line.service_account.sudo().do_deactive()
        return res

    @api.multi
    def prepare_renewal_order(self):
        self.ensure_one()
        order_id = self.env['sale.order'].search(
            [('subscription_id','=',self.id),('subscription_management','=','renew'),('state','=','draft')], limit=1)

        if order_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "views": [[False, "form"]],
                "res_id": order_id.id,
            }

        else:
            return super(SaleSubscription, self).prepare_renewal_order()

    @api.multi
    def prepare_cancel_order(self):
        self.ensure_one()
        res = self.prepare_renewal_order()
        if res and res.has_key('res_id'):
            order_id = res['res_id']
            order = self.env['sale.order'].browse(order_id)
            if self._context.has_key('cancel') and self._context['cancel'] == 1:
                order.write({'subscription_management': 'cancel'})
                order.write({'doc_type': 'cancel'})
            else:
                order.write({'subscription_management': 'close'})
                order.write({'doc_type': 'close'})
        return res

    @api.multi
    def prepare_free_order(self):
        self.ensure_one()
        res = self.prepare_renewal_order()
        if res and res.has_key('res_id'):
            order_id = res['res_id']
            order = self.env['sale.order'].browse(order_id)
            order.write({'subscription_management': 'free'})
            order.write({'doc_type': 'free'})
        return res

    @api.multi
    def _prepare_renewal_order_values(self):
        res = dict()
        for contract in self:
            order_lines = []
            fpos_id = self.env['account.fiscal.position'].get_fiscal_position(contract.partner_id.id)
            for line in contract.recurring_invoice_line_ids:
                order_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.product_id.product_tmpl_id.name,
                    'product_uom': line.uom_id.id,
                    'product_uom_qty': line.quantity,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'name': line.name,
                }))
            addr = contract.partner_id.address_get(['delivery', 'invoice'])
            res[contract.id] = {
                'pricelist_id': contract.pricelist_id.id,
                'partner_id': contract.partner_id.id,
                'partner_invoice_id': addr['invoice'],
                'partner_shipping_id': addr['delivery'],
                'currency_id': contract.pricelist_id.currency_id.id,
                'order_line': order_lines,
                'project_id': contract.analytic_account_id.id,
                'subscription_management': 'renew',
                'note': contract.description,
                'fiscal_position_id': fpos_id,
                'user_id': contract.user_id.id,
                'payment_term_id': contract.partner_id.property_payment_term_id.id,
                'team_id': contract.crm_team_id.id,
                'template_id':contract.quote_template_id.id,
            }
        return res

class SaleSubscriptionLine(models.Model):
    _inherit = "sale.subscription.line"

    is_actual = fields.Boolean('Is actual', default=False)
    service_account = fields.Many2one('account.master', string='Service account')

    @api.multi
    def calculate_actual(self):
        self.ensure_one()

        if self.analytic_account_id.prepaid:
            # Clone original line from order
            self.copy({
                'is_actual': True,
            })
            return

        # get date form, date to
        date_to = fields.Date.from_string(self.analytic_account_id.recurring_next_date)
        periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
        date_from = date_to - relativedelta(**{periods[self.analytic_account_id.recurring_rule_type]: self.analytic_account_id.recurring_interval})
        date_to = date_to - relativedelta(days=1)  # remove 1 day as normal people thinks in term of inclusive ranges.

        # get timesheet groupby date_unit_price
        date_from = self.analytic_account_id.is_manual_date and fields.Date.from_string(self.analytic_account_id.start_date_fee) or date_from
        date_from_str = datetime.strftime(date_from, DEFAULT_SERVER_DATE_FORMAT)
        date_to_str = datetime.strftime(date_to, DEFAULT_SERVER_DATE_FORMAT)

        self.env.cr.execute("""SELECT SUM(unit_amount) as unit_amount, date_unit_price
                                FROM account_analytic_line
                                WHERE subscription_line_id = %s
                                AND account_id=%s 
                                AND date >= %s 
                                AND  date <= %s 
                                GROUP BY date_unit_price
                                ORDER BY date_unit_price """,
                            (self.id, self.analytic_account_id.analytic_account_id.id, date_from_str, date_to_str))
        timesheet_group = self.env.cr.fetchall()

        # create actual line
        uom_day = self.env.ref('product.product_uom_day')
        if timesheet_group:
            for timesheet in timesheet_group:
                quantity = self.analytic_account_id.company_id.project_time_mode_id._compute_quantity(timesheet[0], uom_day)
                self.copy({
                    'actual_quantity': quantity,
                    'sold_quantity': quantity,
                    'uom_id': uom_day.id,
                    'price_unit': timesheet[1],
                    'is_actual': True,
                })
        else:

            price_unit_day = self.uom_id._compute_price(self.price_unit, uom_day)
            if self.uom_id.id == self.env.ref('dgn_config.product_uom_month').id:
                date_to = fields.Date.from_string(self.analytic_account_id.recurring_next_date) - relativedelta(days=1)
                day_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                price_unit_day = price_unit_day * self.uom_id.factor_inv / day_in_month

            self.copy({
                'actual_quantity': 0,
                'sold_quantity': 0,
                'uom_id': uom_day.id,
                'price_unit': price_unit_day,
                'is_actual': True,
            })