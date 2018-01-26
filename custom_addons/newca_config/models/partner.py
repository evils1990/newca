#-*- coding: utf-8 -*-

from odoo import fields,models,api,_
from odoo.exceptions import ValidationError

class Partner(models.Model):
    _inherit = "res.partner"
    # _rec_name = 'vat'

    sale_man_ids=fields.Many2many('res.users','partner_user_saleman_rel',column1='partner_id',column2='sale_man_id',string='Salepersons',default=lambda self: self.env.user)
    vat_counts=fields.Integer('VAT count',compute='_compute_vat_counts')

    invoiced_count = fields.Integer('# of Invoice',compute = '_compute_invoiced_count')

    def _compute_invoiced_count(self):
        sale_data = self.env['account.invoice'].read_group(domain=[('partner_id', 'child_of', self.ids)],
                                                      fields=['partner_id'], groupby=['partner_id'])

        partner_child_ids = self.read(['child_ids'])
        mapped_data = dict([(m['partner_id'][0], m['partner_id_count']) for m in sale_data])
        for partner in self:
            partner_ids = filter(lambda r: r['id'] == partner.id, partner_child_ids)[0]
            partner_ids = [partner_ids.get('id')] + partner_ids.get('child_ids')
            partner.invoiced_count = sum(mapped_data.get(child, 0) for child in partner_ids)

    @api.multi
    def _compute_vat_counts(self):
        for van in self:
            van.vat_counts=self.env['sale.subscription'].search_count([('partner_id','!=',van.id),('partner_id.vat','=',van.vat)])

    @api.onchange('vat')
    def _check_vat(self):
        for van in self:
            van.vat_counts = self.env['sale.subscription'].search_count([('partner_id','!=',van.id),('partner_id.vat','=',van.vat)])

    @api.constrains('phone')
    def _check_phone(self):
        if self.customer == True:
            duplicate=self.search_count([('phone','=',self.phone),('create_uid','=',self.env.uid),('customer','=',True)])
            if duplicate >3 :
                raise ValidationError(_("Input duplicate phone too many time"))

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args=[]
        if name:
            domain=['|',('vat',operator,name),('name',operator,name)]
            ids=self.search(domain,limit=limit)
        else:
            ids=self.search(args,limit=limit)
        return ids.name_get()


class Users(models.Model):
    _inherit = "res.users"

    all_partner_ids=fields.Many2many('res.partner',string='All partners')



