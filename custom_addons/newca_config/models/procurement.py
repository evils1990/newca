from odoo import models


class ProcurementOrder(models.Model):
    _inherit = "procurement.order"

    def _get_stock_move_values(self):
        res = super(ProcurementOrder, self)._get_stock_move_values()
        if self._context.has_key('agency_location'):
            res['location_id'] = self._context['agency_location']
        return res