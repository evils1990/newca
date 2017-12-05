{
    'name': 'NewCA Configuration',
    'version': '1.0.0',
    'Category': 'Sales',
    'sequence': 20,
    'summary': 'Use for NewCA Project',
    'author': '',
    'description': 'Contract Management System',
    'depends': ['base_vat', 'sale_agency', 'stock', 'website_contract','account_invoice_merge'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_view.xml',
        'views/account_view.xml',
    ],
    'qweb': [],
    'demo': [],
    'installable': True,
    'application': True,
}