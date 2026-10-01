{
    'name': 'NT Sale',
    'version': '19.0.1.2.0',
    'category': 'Sales',
    'summary': 'NorthStar sale customisations: fixed discount and truck details from purchase orders',
    'author': 'NorthStar Technologies International Ltd.',
    'depends': ['sale_management', 'sale_stock', 'nt_purchase'],
    'data': [
        'security/ir.model.access.csv',
        'data/product_data.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
