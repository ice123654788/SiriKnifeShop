from django.contrib import admin
from .models import Category, Order, Product, ProductColor, ProductImage, OrderItem
from django.db.models import Sum
from django import forms  
from django.forms.widgets import CheckboxInput, ClearableFileInput
from django.utils.safestring import mark_safe
from django.contrib import messages  
import urllib.parse

# 1. Widget ขั้นเด็ดขาด: ซ่อนช่องติ๊กทิ้งทันที และสร้างปุ่ม "ถอดออก" ที่สั่งงานได้จริง
class CustomDeleteCheckboxWidget(CheckboxInput):
    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        widget_id = attrs.get('id', name) if attrs else name
        return mark_safe(
            f'<div style="display:inline-block;">'
            f'{html}'
            f'<span style="color: #d9534f; cursor: pointer; font-weight: bold; user-select: none;" '
            f'onclick="const cb=document.getElementById(\'{widget_id}\'); if(cb){{cb.checked=!cb.checked; this.style.opacity=cb.checked?\'0.3\':\'1\';}}">ถอดออก</span>'
            f'<script>'
            f'setTimeout(function() {{'
            f'  const cb = document.getElementById("{widget_id}");'
            f'  if(cb) {{ cb.style.display = "none"; if(cb.checked) cb.nextElementSibling.style.opacity = "0.3"; }}'
            f'}}, 50);'
            f'</script>'
            f'</div>'
        )

# 2. ฟอร์มกลางสำหรับบังคับใช้ Widget ลบนี้กับทุก Inline
class CustomDeleteForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'DELETE' in self.fields:
            self.fields['DELETE'].widget = CustomDeleteCheckboxWidget()

# ลงทะเบียน Category
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    verbose_name = 'Category'
    verbose_name_plural = 'Categories'

# 3. นำฟอร์มไปใช้กับ ProductColorInline
class ProductColorInline(admin.TabularInline):
    model = ProductColor
    form = CustomDeleteForm  
    extra = 1

# 4. ฟอร์มสำหรับ ProductImage (สืบทอดจาก CustomDeleteForm เพื่อให้มีปุ่มถอดออกทั้งช่องลบและรูปภาพเดิม)
class ProductImageAdminForm(CustomDeleteForm):
    class Meta:
        model = ProductImage
        fields = '__all__'
        widgets = {
            'image': ClearableFileInput(attrs={'clear_checkbox_label': 'ถอดออก'}),
        }

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageAdminForm  
    extra = 1  

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0  
    tab = False  
    fields = ('product', 'color', 'quantity', 'price')
    readonly_fields = ('product', 'color', 'quantity', 'price')

    class Media:
        js = ('data:text/javascript;charset=utf-8,' + urllib.parse.quote('''
            document.addEventListener("DOMContentLoaded", function() {
                // ค้นหาหัวตารางและข้อมูลในคอลัมน์ที่มีข้อความ Product name แล้วซ่อนทิ้ง
                const headers = document.querySelectorAll("th");
                headers.forEach(th => {
                    if (th.textContent.trim() === "Product name") {
                        const index = Array.from(th.parentNode.children).indexOf(th) + 1;
                        // ซ่อนทั้งหัวตารางและทุกแถวในคอลัมน์นั้น
                        document.querySelectorAll(`th:nth-child(${index}), td:nth-child(${index})`).forEach(el => {
                            el.style.display = "none";
                        });
                    }
                });
            });
        '''),)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'full_name', 'get_ordered_colors', 'total_price', 'status', 'created_at'] 
    list_filter = ['status', 'created_at']
    search_fields = ['full_name', 'id']
    inlines = [OrderItemInline]

    def has_add_permission(self, request):
        return False
    # 👈 ดักเคลียร์ข้อความแจ้งเตือนสีเขียวไม่ให้แสดงผลในหน้านี้
    def changelist_view(self, request, extra_context=None):
        storage = messages.get_messages(request)
        for _ in storage:
            pass
        storage.used = True
        return super().changelist_view(request, extra_context=extra_context)

    def get_ordered_colors(self, obj):
        items = obj.items.all()
        color_list = []
        for item in items:
            prod_name = item.product.name if item.product else "สินค้า"
            color_value = str(item.color).strip() if item.color else ""
            if color_value and color_value.lower() != 'ปกติ' and color_value != '-':
                color_list.append(f"{prod_name} ({color_value})")
            else:
                color_list.append(prod_name)
        return ", ".join(color_list) if color_list else "-"
    get_ordered_colors.short_description = 'สินค้า / สีที่สั่ง'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'price', 'category', 'get_total_sold']
    list_filter = ['category', 'is_best_seller']
    search_fields = ['name']
    inlines = [ProductColorInline, ProductImageInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(total_sold=Sum('orderitem__quantity'))

    def get_total_sold(self, obj):
        return obj.total_sold or 0
    get_total_sold.short_description = 'จำนวนที่ขายได้ (ชิ้น)'
    get_total_sold.admin_order_field = 'total_sold'