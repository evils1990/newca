# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Account Contract Dashboard',
    'version': '1.0',
    'depends': ['sale_contract_asset', 'account_deferred_revenue'],
    'category': 'Accounting',
    'description': """
Accounting Contract Dashboard
========================
It adds dashboards to :
1) Analyse the recurrent revenue and other metrics for contracts
2) Analyse the contracts modifications by salesman and compute their value.
    """,
    'website': 'https://www.odoo.com/page/accounting',
    'category': 'Accounting & Finance',
    'data': [
        'views/account_contract_dashboard_views.xml',
        'views/account_contract_dashboard_templates.xml',
    ],
    'demo': [
    ],
    'qweb': [
        "static/src/xml/account_contract_dashboard.xml",
    ],
    'installable': True,
    'application': False,
    'license': 'OEEL-1',
}
