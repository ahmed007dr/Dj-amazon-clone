"""عقود التقييمات."""

from rest_framework import serializers

from reviews.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """
    التقييم كما يراه العامة.

    ⚠️  اسم المُقيِّم مختصر — لا بريد ولا معرّف.
        صفحة منتج عامة لا تكشف هوية المشترين.
    """

    author = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "rating",
            "title",
            "body",
            "author",
            "is_verified_purchase",
            "helpful_count",
            "is_mine",
            "created_at",
        ]

    def get_author(self, obj) -> str:
        """الاسم الأول والحرف الأول من الأخير — «أحمد م.»"""
        first = (obj.user.first_name or "").strip()
        last = (obj.user.last_name or "").strip()

        if not first:
            return "مستخدم"
        return f"{first} {last[0]}." if last else first

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.user_id == request.user.pk)


class ReviewWriteSerializer(serializers.ModelSerializer):
    """
    ⚠️  `status` غير قابل للكتابة.

    السماح به يعني أن العميل ينشر تقييمه بنفسه متجاوزًا المراجعة.
    """

    class Meta:
        model = Review
        fields = ["id", "product", "rating", "title", "body"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context["request"]
        product = attrs.get("product") or getattr(self.instance, "product", None)

        # تقييم واحد لكل مستخدم لكل منتج
        existing = Review.all_objects.filter(
            product=product, user=request.user, deleted_at__isnull=True
        )
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise serializers.ValidationError(
                {"product": "لديك تقييم لهذا المنتج بالفعل — عدّله بدل إنشاء جديد"}
            )

        return attrs


class AdminReviewSerializer(serializers.ModelSerializer):
    """نسخة الأدمن — تكشف الهوية الكاملة للمراجعة."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name_ar", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "user",
            "user_email",
            "rating",
            "title",
            "body",
            "status",
            "is_verified_purchase",
            "helpful_count",
            "rejection_reason",
            "moderated_at",
            "created_at",
        ]
        read_only_fields = fields


class ModerateReviewSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        if not attrs["approved"] and not attrs.get("reason"):
            raise serializers.ValidationError(
                {"reason": "سبب الرفض مطلوب — الرفض بلا سبب لا يُشرح للعميل"}
            )
        return attrs


class ProductRatingSerializer(serializers.Serializer):
    average = serializers.DecimalField(max_digits=3, decimal_places=2, read_only=True)
    count = serializers.IntegerField(read_only=True)
    distribution = serializers.DictField(read_only=True)
