# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from dateutil.relativedelta import relativedelta


class SaleSubscription(models.Model):
    _inherit = "sale.subscription"

    cancel_date = fields.Date(string='Cancel Date of Subscription')

    @api.model
    def auto_cron_account_analytic_account(self):
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
    def auto_cron_cancel(self):
        today = fields.Date.today()

        # set to close if data is passed
        domain_close = [('cancel_date', '<', today), ('state', 'in', ['pending', 'open'])]
        subscriptions_close = self.search(domain_close)

        subscriptions_close.write({'state': 'cancel'})


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

            else:
                order.write({'subscription_management': 'close'})
        return res

    @api.multi
    def prepare_free_order(self):
        self.ensure_one()
        res = self.prepare_renewal_order()
        if res and res.has_key('res_id'):
            order_id = res['res_id']
            order = self.env['sale.order'].browse(order_id)
            order.write({'subscription_management': 'free'})
        return res

    @api.multi
    def check_subscription_vat(self,vat):
        res={}
        res=self.search([('partner_id','=',vat)])
        return res

