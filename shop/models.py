from django.db import models
from django.contrib.auth.models import User

# 1. ตารางหมวดหมู่สินค้า
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Category Name")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Slug")

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

# 2. ตารางสินค้าหลัก
class Product(models.Model):
    name = models.CharField(max_length=200, verbose_name="ชื่อสินค้า")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ประเภทสินค้า")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคา")
    # 📌 เพิ่มฟิลด์ stock เผื่อไว้สำหรับสินค้าที่ไม่มีตัวเลือกสี (สินค้าแบบธรรมดา)
    stock = models.PositiveIntegerField(default=0, verbose_name="จำนวนคงเหลือ (กรณีไม่มีตัวเลือกสี)")
    description = models.TextField(blank=True, null=True, verbose_name="รายละเอียดสินค้า")
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name="รูปภาพสินค้า")
    is_best_seller = models.BooleanField(default=False, verbose_name="สินค้าขายดีประจำร้าน")

    @property
    def total_stock(self):
        color_stock_sum = sum(color.stock for color in self.colors.all())
        if self.colors.exists():
            return color_stock_sum
        return self.stock

    def __str__(self):
        return self.name

# 3. รูปภาพเพิ่มเติมของสินค้า (Gallery)
class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='product_gallery/')

    def __str__(self):
        return f"Image for {self.product.name}"

# 4. ตัวเลือกสีและสต็อกแยกตามชิ้น
class ProductColor(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='colors', verbose_name="สินค้า")
    color_name = models.CharField(max_length=50, verbose_name="ชื่อสี / ตัวเลือก")
    stock = models.PositiveIntegerField(default=0, verbose_name="จำนวนคงเหลือ (สต็อก)")

    def __str__(self):
        return f"{self.product.name} - {self.color_name} (เหลือ {self.stock} ชิ้น)"

# 5. ตารางคำสั่งซื้อ
class Order(models.Model):
    STATUS_CHOICES = [
        ("รอตรวจสอบสลิป", "รอตรวจสอบสลิป"),
        ("ชำระเงินสำเร็จ", "ชำระเงินสำเร็จ"),
        ("สลิปไม่ถูกต้อง", "สลิปไม่ถูกต้อง"),
    ]
    
    # 🟢 ประกาศ status ครั้งเดียวและผูก choices ให้ถูกต้องตรงนี้
    status = models.CharField(
        max_length=50, 
        choices=STATUS_CHOICES, 
        default="รอชำระเงิน / อัปโหลดสลิป", 
        verbose_name="สถานะคำสั่งซื้อ"
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="ผู้สั่งซื้อ")
    full_name = models.CharField(max_length=150, verbose_name="ชื่อ-นามสกุล ผู้รับ")
    phone = models.CharField(max_length=20, verbose_name="เบอร์โทรศัพท์")
    address = models.TextField(verbose_name="ที่อยู่จัดส่ง")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดรวมทั้งหมด")
    slip_image = models.ImageField(upload_to='slips/', blank=True, null=True, verbose_name="หลักฐานการชำระเงิน (สลิป)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่สั่งซื้อ")

    def __str__(self):
        return f"ออเดอร์ #{self.id} - {self.full_name}"

# 6. ตารางแชท
class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="ผู้ส่ง")
    message = models.TextField(blank=True, null=True, verbose_name="ข้อความ")
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True, verbose_name="รูปภาพ")
    is_admin_reply = models.BooleanField(default=False, verbose_name="ตอบโดยแอดมินหรือไม่")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="เวลาที่ส่ง")

    def __str__(self):
        return f"{self.user.username} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

# ใน models.py เพิ่มหรือตรวจสอบให้แน่ใจว่ามีตาราง OrderItem ประมาณนี้ครับ
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255) # บันทึกชื่อไว้กันสินค้าถูกลบ
    color = models.CharField(max_length=50, default='ปกติ')
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2) # ราคา ณ ตอนซื้อ
    
    @property
    def total_revenue(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_name} ({self.color}) x {self.quantity}"