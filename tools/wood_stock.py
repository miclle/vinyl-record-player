"""Shared woodworking catalog for the drawing pack and assembly guide."""


WOOD_STOCK_CATALOG = [
    ('W01', 1, 'SideLeft', '左右侧板', '块', '胡桃木饰面；基材待定'),
    ('W02', 1, 'Slat01', '横向木格栅', '条', '木饰条；木种待定'),
    ('W03', 2, 'Bottom', '底板', '块', '木质板材；基材待定'),
    ('W04', 2, 'Back', '后板', '块', '木质板材；基材待定'),
    ('W06', 2, 'Baffle', '倾斜扬声器障板', '块', '木质板材；斜口按精确轮廓修切'),
    ('W07', 2, 'AcousticRoof', '三音腔共用顶板', '块', '木质板材；基材待定'),
    ('W08', 2, 'AcousticRear', '左右全频腔后板', '块', '一个 CAD 对象内的两块独立木板'),
    ('W09', 2, 'AcousticDividerLeft', '低音腔全深隔板', '块', '木质板材；前缘按斜线修切'),
    ('W10', 2, 'RearSupport', '后部承托梁', '件', '一个 CAD 对象内的两块独立木梁'),
    ('W11', 2, 'FloatingDeck', '浮动承载台面', '块', '木质结构板；机芯开口仍待设计'),
]

RETIRED_WOOD_CODES = {
    'W05': '原独立下横梁与底板完全重叠，已取消；编号保留不重排。',
}


def stock_rows(cards):
    """Return validated stock rows in stable assembly-guide order."""
    grouped = {}
    for card in cards:
        if 'stock_mm' not in card:
            continue
        key = card['ids'][0]
        row = grouped.setdefault(key, {
            'ids': [],
            'quantity': 0,
            'stock_mm': card['stock_mm'],
            'stock_note': card['stock_note'],
        })
        if row['stock_mm'] != card['stock_mm'] or row['stock_note'] != card['stock_note']:
            raise ValueError(f'Inconsistent woodworking data for {key}')
        row['quantity'] += card['quantity']
        for name in card['ids']:
            if name not in row['ids']:
                row['ids'].append(name)

    expected = {spec[2] for spec in WOOD_STOCK_CATALOG}
    actual = set(grouped)
    if actual != expected:
        raise ValueError(
            'Woodworking catalog mismatch: '
            f'missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}'
        )

    rows = []
    for code, page, key, title, unit, material in WOOD_STOCK_CATALOG:
        rows.append({
            'code': code,
            'page': page,
            'key': key,
            'title': title,
            'unit': unit,
            'material': material,
            **grouped[key],
        })
    return rows
