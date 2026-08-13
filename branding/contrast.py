"""
حساب نسبة التباين — WCAG 2.1.

⚠️  التباين ليس رأيًا جماليًا.

    نص رماديّ فاتح على أبيض يبدو «أنيقًا» على شاشة المصمّم، ويصير
    غير مقروء على هاتف تحت الشمس أو لعين ضعيفة. الصيغة هنا هي
    نفسها التي تستخدمها أدوات التدقيق، فما يمرّ هنا يمرّ عندها.

المرجع: https://www.w3.org/TR/WCAG21/#contrast-minimum
"""

#: الحد الأدنى للنص العادي
AA_NORMAL_TEXT = 4.5

#: الحد الأدنى للنص الكبير (≥ 18.66px عريض أو ≥ 24px)
AA_LARGE_TEXT = 3.0


def parse_hex(value: str) -> tuple[int, int, int]:
    """`#rgb` أو `#rrggbb` → (r, g, b)."""
    digits = value.lstrip("#")

    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)

    if len(digits) != 6:
        raise ValueError(f"لون غير صالح: {value}")

    return tuple(int(digits[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(color: str) -> float:
    """
    السطوع النسبي.

    ⚠️  ليس متوسط القنوات: العين أشدّ حساسية للأخضر بكثير، ولذلك
        المعاملات (0.2126 · 0.7152 · 0.0722) غير متساوية.
    """
    channels = []
    for raw in parse_hex(color):
        value = raw / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)

    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """نسبة التباين بين لونين — من 1:1 (متطابقان) إلى 21:1 (أبيض/أسود)."""
    first = relative_luminance(foreground)
    second = relative_luminance(background)

    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def passes_aa(foreground: str, background: str, *, large_text: bool = False) -> bool:
    threshold = AA_LARGE_TEXT if large_text else AA_NORMAL_TEXT
    return contrast_ratio(foreground, background) >= threshold


def audit_palette(palette) -> list[dict]:
    """
    تقرير تباين كامل للوحة — للعرض في شاشة الأدمن.

    يعيد **كل** الأزواج لا الفاشلة وحدها: إظهار الناجح يجعل الأدمن
    يرى أثر تعديله لحظةً بلحظة بدل أن يخمّن.
    """
    pairs = [
        ("text_on_bg", "النص على الخلفية", palette.text, palette.bg),
        ("text_on_surface", "النص على السطح", palette.text, palette.surface),
        ("muted_on_surface", "الخافت على السطح", palette.text_muted, palette.surface),
        ("on_primary", "النص فوق الأساسي", palette.on_primary, palette.primary),
        ("primary_on_bg", "الأساسي على الخلفية", palette.primary, palette.bg),
        ("danger_on_surface", "الخطر على السطح", palette.danger, palette.surface),
        ("success_on_surface", "النجاح على السطح", palette.success, palette.surface),
    ]

    report = []
    for key, label, foreground, background in pairs:
        ratio = contrast_ratio(foreground, background)
        report.append(
            {
                "key": key,
                "label": label,
                "foreground": foreground,
                "background": background,
                "ratio": round(ratio, 2),
                "passes_aa": ratio >= AA_NORMAL_TEXT,
                "passes_aa_large": ratio >= AA_LARGE_TEXT,
            }
        )
    return report
