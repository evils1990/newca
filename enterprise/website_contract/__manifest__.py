{
    'name': 'Subscription Management',
    'category': 'Website',
    'sequence': 32,
    'summary': 'Subscriptions Management Frontend for your customers',
    'version': '1.0',
    'description': """
Use this app to manage Subscriptions:
Features:
    - Create & edit susbcriptions with sales orders (automatic creation on confirmation)
    - Generate invoice and credit card payments automatically at fixed intervals
    - Let your customer edit their subscriptions themselves (options, close their contract) with granular control
        """,
    'depends': [
        'sale_contract',
        'website_sale',
        'website_portal',
        'website_quote',
        'website_payment',
        'account_contract_dashboard',
    ],
    'data': [
        'views/sale_subscription_templates.xml',
        'views/sale_subscription_views.xml',
        'views/payment_acquirer_views.xml',
        'security/ir.model.access.csv',
        'security/portal_contract_security.xml',
        'data/data.xml'
    ],
    'qweb': [
        'static/src/xml/*.xml'
    ],
    'demo': [
        #if any, demo data should be created using yml files, in the same flavour then in account_asset
        'data/demo.xml',
        'data/demo.yml',
    ],
    'installable': True,
    'application': True,
    'license': 'OEEL-1',
}
