# -*- coding: utf-8 -*-
from odoo import fields, models, api,_
from dateutil.relativedelta import relativedelta
import datetime
import sys;
reload(sys);
sys.setdefaultencoding("utf8")


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    location_id = fields.Many2one('stock.location', 'Sale Location', domain=[('usage', '=', 'internal')])


class SaleOrder(models.Model):
    _inherit = "sale.order"

    end_date = fields.Date(string='End Date of Subscription')
    cancel_date = fields.Date(string='Cancel Date of Subscription')
    free_day_qty = fields.Integer(string='Quantity',default=0)
    free_day_description = fields.Char(string='Description')
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('submit', 'Quotation Submitted'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

    subscription_management = fields.Selection(string='Subscription Management',
                                               selection=[('create', 'Creation'), ('renew', 'Renewal'),
                                                          ('upsell', 'Upselling'),('close', 'Close'),
                                                          ('cancel', 'Cancel'),
                                                          ('free', 'Free time')])
    subscription_state = fields.Selection(related='subscription_id.state')
    template_id = fields.Many2one('sale.quote.template', 'Quotation Template', readonly=True, required=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})


    @api.multi
    def sale_submit(self):
        self.write({'state': 'submit'})

    @api.multi
    def action_confirm(self):
        self.ensure_one()
        if self.subscription_management in ['close','cancel']:
            reason_wizard = self.env.ref('sale_contract.sale_subscription_close_reason_wizard_action').read()[0]
            if self.subscription_management == 'cancel':
                reason_wizard.update({'context': {'cancel':1}})
            return reason_wizard

        if self.subscription_management == 'free':
            if self.subscription_id:
                next_invoice_day = fields.Date.from_string(self.subscription_id.recurring_next_date) + datetime.timedelta(days=self.free_day_qty)
                self.subscription_id.write({'recurring_next_date':next_invoice_day})
            self.write({'state': 'done'})
            return

        subscription_id = self.subscription_id and self.subscription_id.id or False
        self.write({'subscription_id': False}) # Dirty hack
        res = super(SaleOrder, self).action_confirm()
        self.write({'subscription_id': subscription_id})


        for order in self:
            if order.subscription_id:

                #set Date of Next Invoice
                if self.subscription_management == 'create':
                    order.subscription_id.sudo().write({'recurring_next_date':order.subscription_id.date_start})
                    if order.free_day_qty > 0:
                        order.subscription_id.write({'recurring_next_date': fields.Date.from_string(order.subscription_id.recurring_next_date) + datetime.timedelta(days=order.free_day_qty)})

                else:
                    if not order.subscription_management:
                        order.subscription_management = 'upsell'

                    if order.subscription_management == 'renew':

                        # reduce 'recurring_next_date' because Super called increment_period()
                        current_date = order.subscription_id.recurring_next_date or \
                                       self.default_get(['recurring_next_date'])[
                                           'recurring_next_date']
                        periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
                        new_date = fields.Date.from_string(current_date) - relativedelta(
                            **{periods[
                                   order.subscription_id.recurring_rule_type]: order.subscription_id.recurring_interval})
                        order.subscription_id.write({'recurring_next_date': new_date})

                        # write data form SO to Subscription
                        to_remove = [(2, line.id, 0) for line in order.subscription_id.recurring_invoice_line_ids]
                        order.subscription_id.sudo().write(
                            {'recurring_invoice_line_ids': to_remove, 'description': order.note,
                             'pricelist_id': order.pricelist_id.id, 'partner_id': order.partner_id.id,
                             'template_id': order.template_id and order.template_id.contract_template.id or False})

                        #add new lines or increment quantities on existing lines
                        values = {'recurring_invoice_line_ids': []}
                        for line in order.order_line:
                            if line.product_id.recurring_invoice:
                                recurring_line_id = False
                                if line.product_id in [subscr_line.product_id for subscr_line in
                                                       order.subscription_id.recurring_invoice_line_ids]:
                                    for subscr_line in order.subscription_id.recurring_invoice_line_ids:
                                        if subscr_line.product_id == line.product_id and subscr_line.uom_id == line.product_uom:
                                            recurring_line_id = subscr_line.id
                                            quantity = subscr_line.sold_quantity
                                            break
                                if recurring_line_id:
                                    values['recurring_invoice_line_ids'].append((1, recurring_line_id, {
                                        'sold_quantity': quantity + line.product_uom_qty,
                                    }))
                                else:
                                    values['recurring_invoice_line_ids'].append((0, 0, {
                                        'product_id': line.product_id.id,
                                        'analytic_account_id': order.subscription_id.id,
                                        'name': line.name,
                                        'sold_quantity': line.product_uom_qty,
                                        'uom_id': line.product_uom.id,
                                        'price_unit': line.price_unit,
                                        'discount': line.discount if line.order_id.subscription_management == 'renew' else False,
                                    }))
                        order.subscription_id.sudo().write(values)
                order.action_done()
                order.subscription_id.sudo().set_pending()
        return res


    @api.multi
    def action_non_subscription_invoice_create(self):
        order_lines = self.env['sale.order.line']
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        lines = []
        # Filter subscription line by invoice qty smaller than zero
        for order in sale_orders:
            for line in order.order_line:
                if line.product_id.recurring_invoice:
                    lines.append([line.id, line.qty_to_invoice])  # mark to revert
                    line.write({'qty_to_invoice': -1})

        sale_orders.action_invoice_create()

        # Do revert
        for line in lines:
            line_row = order_lines.browse(line[0])
            line_row.write({'qty_to_invoice': line[1]})


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.multi
    def _action_procurement_create(self):

        if not self._context.has_key('agency_location'):
            for record in self:
                if record.order_id and record.order_id.team_id and record.order_id.team_id.crm_type == 'agency':
                    context = {'agency_location': self.order_id.team_id.location_id.id } # Force delivery from team location
                    return super(SaleOrderLine, self).with_context(context)._action_procurement_create()

        return super(SaleOrderLine, self)._action_procurement_create()


class SaleSubscriptionCloseReasonWizard(models.TransientModel):
    _inherit = "sale.subscription.close.reason.wizard"

    @api.multi
    def set_close_cancel(self):
        self.ensure_one()
        active_id = self.env.context.get('active_id')
        if self.env.context.has_key('active_model') and self.env.context.get('active_model') == 'sale.order':
            order = self.env['sale.order'].browse(active_id)
            active_id = order.subscription_id.id
            order.write({'state': 'done'})

        subscription = self.env['sale.subscription'].browse(active_id)
        subscription.close_reason_id = self.close_reason_id

        if self.env.context.get('cancel'):
            subscription.set_cancel()
            subscription.write({'cancel_date': order.cancel_date})
            subscription.write({'close_reason_id': self.close_reason_id.id})

        else:
            subscription.set_close()
            subscription.write({'date': order.end_date})
            subscription.write({'close_reason_id': self.close_reason_id.id})


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"
    _description = "Sales Advance Payment Invoice"

    advance_payment_method = fields.Selection([
        ('nonsubscription', 'Invoiceable lines (non subscription)'),
        ('delivered', 'Invoiceable lines'),
        ('all', 'Invoiceable lines (deduct down payments)'),
        ('percentage', 'Down payment (percentage)'),
        ('fixed', 'Down payment (fixed amount)')
    ], string='What do you want to invoice?', default='nonsubscription', required=True)

    @api.multi
    def create_invoices(self):
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        if self.advance_payment_method == 'nonsubscription':
            res = sale_orders.action_non_subscription_invoice_create()
        else:
            res = super(SaleAdvancePaymentInv, self).create_invoices()
        return res


class SaleReport(models.Model):
    _inherit = "sale.report"

    doc_type = fields.Selection(string='Doc type',
                                selection=[('create', 'Creation'),
                                           ('renew_change_service', 'Change service'),
                                           ('renew_reopen_service', 'Re-Open service'),
                                           ('renew_change_payment_period', 'Change payment period'),
                                           ('close', 'Close'),
                                           ('cancel', 'Cancel'),
                                           ('free', 'Free time')], default='create')

    def _select(self):
        select_str = """
            WITH currency_rate as (%s)
             SELECT min(l.id) as id,
                    l.product_id as product_id,
                    t.uom_id as product_uom,
                    sum(l.product_uom_qty / u.factor * u2.factor) as product_uom_qty,
                    sum(l.qty_delivered / u.factor * u2.factor) as qty_delivered,
                    sum(l.qty_invoiced / u.factor * u2.factor) as qty_invoiced,
                    sum(l.qty_to_invoice / u.factor * u2.factor) as qty_to_invoice,
                    sum(l.price_total / COALESCE(cr.rate, 1.0)) as price_total,
                    sum(l.price_subtotal / COALESCE(cr.rate, 1.0)) as price_subtotal,
                    count(*) as nbr,
                    s.name as name,
                    s.date_order as date,
                    s.state as state,
                    s.partner_id as partner_id,
                    s.user_id as user_id,
                    s.company_id as company_id,
                    extract(epoch from avg(date_trunc('day',s.date_order)-date_trunc('day',s.create_date)))/(24*60*60)::decimal(16,2) as delay,
                    t.categ_id as categ_id,
                    s.pricelist_id as pricelist_id,
                    s.project_id as analytic_account_id,
                    s.team_id as team_id,
                    p.product_tmpl_id,
                    partner.country_id as country_id,
                    partner.commercial_partner_id as commercial_partner_id,
                    sum(p.weight * l.product_uom_qty / u.factor * u2.factor) as weight,
                    sum(p.volume * l.product_uom_qty / u.factor * u2.factor) as volume,
                    s.doc_type as doc_type
        """ % self.env['res.currency']._select_companies_rates()
        return select_str

    def _group_by(self):
        group_by_str = """
            GROUP BY l.product_id,
                    l.order_id,
                    t.uom_id,
                    t.categ_id,
                    s.name,
                    s.date_order,
                    s.partner_id,
                    s.user_id,
                    s.state,
                    s.company_id,
                    s.pricelist_id,
                    s.project_id,
                    s.team_id,
                    p.product_tmpl_id,
                    partner.country_id,
                    partner.commercial_partner_id,
                    s.doc_type
        """
        return group_by_str

