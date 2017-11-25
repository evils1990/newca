from odoo import api, fields, models

class account_payment(models.Model):
    _inherit = 'account.payment'

    payment_num = fields.Char(string='Payment Number')

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def get_reconciliation_proposition(self, account_id, partner_id=False):
        """ Returns two lines whose amount are opposite """

        # Get pairs
        partner_id_condition = partner_id and 'AND partner_id = %(partner_id)s' or ''
        query = """
                    SELECT id
                    FROM account_move_line
                    WHERE NOT reconciled
                    AND account_id = %(account_id)s
                    {partner_id_condition}
                    ORDER BY date asc
                """.format(**locals())
        self.env.cr.execute(query, locals())
        pairs = self.env.cr.fetchall()

        # Apply ir_rules by filtering out
        pairs = [element for tupl in pairs for element in tupl]

        # Return lines formatted
        if len(pairs) > 0:
            target_currency = (
                              self.currency_id and self.amount_currency) and self.currency_id or self.company_id.currency_id
            lines = self.browse(pairs)
            return lines.prepare_move_lines_for_reconciliation_widget(target_currency=target_currency)
        return []

    @api.model
    def process_reconciliations(self, data):
        """ Used to validate a batch of reconciliations in a single call
            :param data: list of dicts containing:
                - 'type': either 'partner' or 'account'
                - 'id': id of the affected res.partner or account.account
                - 'mv_line_ids': ids of exisiting account.move.line to reconcile
                - 'new_mv_line_dicts': list of dicts containing values suitable for account_move_line.create()
        """
        for datum in data:
            if len(datum['mv_line_ids']) >= 1 or len(datum['mv_line_ids']) + len(datum['new_mv_line_dicts']) >= 2:
                self.env['account.move.line'].browse(datum['mv_line_ids']).process_reconciliation(datum['new_mv_line_dicts'])