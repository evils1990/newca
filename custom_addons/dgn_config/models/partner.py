# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import time
import re
import unicodedata


class Partner(models.Model):
    _inherit = "res.partner"

    personal_id_number = fields.Char(string='Personal ID Number')
    issued_date = fields.Date(string='Issued date')
    issued_address = fields.Char(string='Issued address')
    customer = fields.Boolean(string='Is a Customer', default=False,
                              help="Check this box if this contact is a customer.")
    total_invoiced_cus = fields.Monetary(compute='_invoice_total_cus', string="Total Invoiced",
                                         groups='account.group_account_invoice')

    @api.multi
    def _invoice_total_cus(self):
        account_invoice_report = self.env['account.invoice.report']
        if not self.ids:
            self.total_invoiced_cus = 0.0
            return True

        user_currency_id = self.env.user.company_id.currency_id.id
        all_partners_and_children = {}
        all_partner_ids = []
        for partner in self:
            # price_total is in the company currency
            all_partners_and_children[partner] = self.search([('id', 'child_of', partner.id)]).ids
            all_partner_ids += all_partners_and_children[partner]

        # searching account.invoice.report via the orm is comparatively expensive
        # (generates queries "id in []" forcing to build the full table).
        # In simple cases where all invoices are in the same currency than the user's company
        # access directly these elements

        # generate where clause to include multicompany rules
        where_query = account_invoice_report._where_calc([
            ('partner_id', 'in', all_partner_ids), ('state', 'not in', ['draft', 'cancel', 'paid']),
            ('company_id', '=', self.env.user.company_id.id),
            ('type', 'in', ('out_invoice', 'out_refund'))
        ])
        account_invoice_report._apply_ir_rules(where_query, 'read')
        from_clause, where_clause, where_clause_params = where_query.get_sql()

        # price_total is in the company currency
        query = """
                          SELECT SUM(price_total) as total, partner_id
                            FROM account_invoice_report account_invoice_report
                           WHERE %s
                           GROUP BY partner_id
                        """ % where_clause
        self.env.cr.execute(query, where_clause_params)
        price_totals = self.env.cr.dictfetchall()
        for partner, child_ids in all_partners_and_children.items():
            partner.total_invoiced_cus = sum(
                price['total'] for price in price_totals if price['partner_id'] in child_ids)

    @api.one
    @api.constrains('company_type', 'personal_id_number', 'vat')
    def _check_identity(self):
        if self.customer == True:
            if self.company_type == 'person':
                duplicate = self.search([('personal_id_number','=', self.personal_id_number),('id','!=', self.id)], limit=1)
                if duplicate:
                    raise ValidationError(_("There is already a person with the same ID"))
            elif self.company_type == 'company':
                duplicate = self.search([('vat', '=', self.vat), ('id', '!=', self.id)],limit=1)
                if duplicate:
                    raise ValidationError(_("There is already a company with the same TIN"))

    @api.one
    @api.constrains('phone')
    def _check_phone(self):
        if self.customer == True:
            if len(self.phone) < 10:
                raise ValidationError(_("You must enter length of phone greater than or equal 10 characters."))

    @api.one
    def set_code_customer(self):
        if self.customer == True:
            if self.company_type == 'company':
                self.ref = self.vat
            else:
                customer_name = self.name
                customer_name = customer_name.encode('utf-8')
                customer_name = customer_name.decode('utf-8')
                customer_name = re.sub(u'Đ', 'D', customer_name)
                customer_name = re.sub(u'đ', 'd', customer_name)
                customer_name = unicodedata.normalize('NFKD', unicode(customer_name)).encode('ASCII', 'ignore')
                split_name = filter(lambda x: len(x.strip(' \t\n\r')) > 0 , customer_name.split(' '))
                it_name = split_name[-1]
                for index in range(len(split_name) - 1):
                    it_name = it_name + split_name[index][0]

                self.ref = (time.strftime("%Y")[-2:] + '-'+ it_name + '-' + self.phone[-5:]).lower()
