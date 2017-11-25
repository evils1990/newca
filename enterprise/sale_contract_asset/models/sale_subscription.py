from odoo import models, fields, api


class SaleSubscription(models.Model):
    _name = "sale.subscription"
    _inherit = "sale.subscription"

    asset_category_id = fields.Many2one('account.asset.category', 'Deferred Revenue Category',
                                        help="This asset category will be applied to the lines of the contract's invoices.",
                                        domain="[('type','=','sale')]")

    @api.onchange('template_id')
    def onchange_template_asset(self):
        if self.template_id.template_asset_category_id:
            self.asset_category_id = self.template_id.template_asset_category_id.id

    def _prepare_invoice_lines(self, fiscal_position_id):
        self.ensure_one()
        inv_lines = super(SaleSubscription, self)._prepare_invoice_lines(fiscal_position_id)
        fiscal_position = self.env['account.fiscal.position'].browse(fiscal_position_id)

        for line in inv_lines:
            asset_category = False
            if self.asset_category_id:
                asset_category = self.asset_category_id
            elif line[2].get('product_id'):
                Product = self.env['product.product'].browse([line[2]['product_id']])
                asset_category = Product.product_tmpl_id.deferred_revenue_category_id

            # Set corresponding account
            if asset_category:
                line[2]['asset_category_id'] = asset_category.id
                account = fiscal_position.map_account(asset_category.account_asset_id)
                line[2]['account_id'] = account.id

        return inv_lines


class SaleSubscriptionTemplate(models.Model):
    _inherit = "sale.subscription.template"

    template_asset_category_id = fields.Many2one('account.asset.category', 'Deferred Revenue Category',
                                        help="This asset category will be set on the subscriptions that have this template.",
                                        domain="[('type','=','sale')]", company_dependent=True)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.multi
    def _prepare_invoice_line(self, qty):
        """
            For recurring products, add the deferred revenue category on the invoice line
        """
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)
        if self.product_id.recurring_invoice:
            asset_category = self.order_id.subscription_id.template_id.template_asset_category_id
            if asset_category:
                account = self.order_id.fiscal_position_id.map_account(asset_category.account_asset_id)
                res['asset_category_id'] = asset_category.id
                res['account_id'] = account.id
        return res
