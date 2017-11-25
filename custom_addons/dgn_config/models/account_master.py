from odoo import api, fields, models, _


class AccountMaster(models.Model):
    _name = "account.master"

    customer_id = fields.Many2one('res.partner', string='Customer', domain=[('customer', '=', True)], required=True)
    image_medium = fields.Binary(related='customer_id.image_medium', readonly=True)
    name = fields.Char(string='User Name', required=True)
    password = fields.Char(string='Password', default='', invisible=True, copy=False, required=True)
    cus_address = fields.Char(string='Customer Address')
    cus_phone = fields.Char(string='Customer Phone')
    cus_email = fields.Char(string='Customer Email')
    pool_1 = fields.Char(string='Pool')
    group = fields.Char(string='Group')
    policy = fields.Char(string='Policy')
    ip_add = fields.Char(string='IP Address')
    product_id = fields.Many2one('product.product', string='Product')
    state = fields.Selection(
        [('deactive', 'Deactive'),('active', 'Active')],
        'Status', readonly=True, copy=False, default='deactive')
    onu_info = fields.Char(string='ONU Info')
    _sql_constraints = [('uniq_name', 'unique(name)', _("The name of user account must be unique !"))]

    @api.onchange('customer_id')
    def _onchange_customer_name(self):
        self.ensure_one()
        if self.customer_id:
            self.cus_address = self.customer_id.street or self.customer_id.street2
            self.cus_phone = self.customer_id.phone or self.customer_id.mobile
            self.cus_email = self.customer_id.email

    @api.one
    def do_active(self):
        self.write({'state': 'active'})

    @api.one
    def do_deactive(self):
        self.write({'state': 'deactive'})

