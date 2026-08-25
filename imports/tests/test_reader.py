"""
Cell coercion and header matching.

⚠️  Every case here is a real failure mode of a real spreadsheet, not a
    hypothetical. Excel decides types on its own, and the admin types Arabic
    digits because that is what their keyboard produces.
"""

import datetime as dt
from decimal import Decimal

import pytest

from imports import spec
from imports.reader import CellError, coerce


class TestNumbers:
    def test_arabic_indic_digits_are_read(self):
        """
        ⚠️  A price typed on an Arabic keyboard arrives as «٤٥٫٥٠».

            Every numeric parser in Python rejects it, and rejecting the row
            makes the importer unusable for exactly the people it is for.
        """
        assert coerce("٤٥٫٥٠", spec.Kind.MONEY) == Decimal("45.50")

    def test_thousands_separators_are_stripped(self):
        assert coerce("1,250.00", spec.Kind.MONEY) == Decimal("1250.00")

    def test_money_is_quantised_not_left_to_the_database(self):
        """
        ⚠️  45.006 is silently rounded on save, so the file and the catalogue
            disagree with nothing to explain why. Rounding here makes the stored
            value the one the dry run reported.
        """
        assert coerce("45.006", spec.Kind.MONEY) == Decimal("45.01")

    def test_excel_writes_whole_numbers_with_a_decimal_point(self):
        """`int("12.0")` raises; the integer column must still accept it."""
        assert coerce("12.0", spec.Kind.INT) == 12
        assert coerce(12.0, spec.Kind.INT) == 12

    def test_a_fractional_integer_is_rejected(self):
        with pytest.raises(CellError):
            coerce("12.5", spec.Kind.INT)

    def test_words_are_rejected_with_the_value_in_the_message(self):
        with pytest.raises(CellError) as caught:
            coerce("خمسة", spec.Kind.MONEY)
        assert "خمسة" in str(caught.value)

    def test_blank_is_none_not_zero(self):
        """
        ⚠️  An empty price cell means "not stated", and zero means free.
            Collapsing them publishes a catalogue priced at nothing.
        """
        assert coerce("", spec.Kind.MONEY) is None
        assert coerce(None, spec.Kind.INT) is None


class TestIdentifiers:
    def test_a_numeric_barcode_keeps_its_digits(self):
        """
        ⚠️  Excel stores a long barcode as a float, and `str(6.22e12)` is not a
            barcode. Going through `int` first is what preserves it.
        """
        assert coerce(6221234567890.0, spec.Kind.TEXT) == "6221234567890"

    def test_whitespace_around_a_sku_is_trimmed(self):
        assert coerce("  MED-001  ", spec.Kind.TEXT) == "MED-001"


class TestDates:
    def test_iso(self):
        assert coerce("2027-06-30", spec.Kind.DATE) == dt.date(2027, 6, 30)

    def test_day_first_with_slashes(self):
        """The format an Egyptian admin writes without thinking about it."""
        assert coerce("30/06/2027", spec.Kind.DATE) == dt.date(2027, 6, 30)

    def test_a_real_datetime_from_excel(self):
        assert coerce(dt.datetime(2027, 6, 30, 13, 5), spec.Kind.DATE) == dt.date(2027, 6, 30)

    def test_arabic_digits_in_a_date(self):
        assert coerce("٢٠٢٧-٠٦-٣٠", spec.Kind.DATE) == dt.date(2027, 6, 30)

    def test_nonsense_is_rejected(self):
        with pytest.raises(CellError):
            coerce("قريبًا", spec.Kind.DATE)


class TestBooleans:
    @pytest.mark.parametrize("raw", ["نعم", "yes", "1", "TRUE", "صح"])
    def test_yes(self, raw):
        assert coerce(raw, spec.Kind.BOOL) is True

    @pytest.mark.parametrize("raw", ["لا", "no", "0", "FALSE"])
    def test_no(self, raw):
        assert coerce(raw, spec.Kind.BOOL) is False

    def test_blank_is_none_so_the_default_applies(self):
        assert coerce("", spec.Kind.BOOL) is None

    def test_anything_else_is_an_error_not_a_guess(self):
        with pytest.raises(CellError):
            coerce("ربما", spec.Kind.BOOL)


class TestAttributes:
    def test_pairs(self):
        assert coerce("size=M;color=blue", spec.Kind.ATTRS) == {"size": "M", "color": "blue"}

    def test_arabic_comma_separates_too(self):
        assert coerce("size=M،color=blue", spec.Kind.ATTRS) == {"size": "M", "color": "blue"}

    def test_a_pair_without_an_equals_sign_is_an_error(self):
        with pytest.raises(CellError):
            coerce("size M", spec.Kind.ATTRS)
