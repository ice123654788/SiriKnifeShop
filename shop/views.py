from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Sum, F, Value, Count
from django.db.models.functions import Coalesce
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.utils import timezone
from datetime import datetime, timedelta
from .forms import ThaiAuthenticationForm, ThaiUserCreationForm
from .models import Category, ChatMessage, Order, OrderItem, Product, ProductColor

# 1. แสดงรายการสินค้าทั้งหมด (รองรับการกรองหมวดหมู่, ค้นหา และคำนวณสต็อกรวม)
def product_list(request):
    categories = Category.objects.all()
    category_slug = request.GET.get('category')
    search_query = request.GET.get('q')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    products = Product.objects.all()

    # กรองตามหมวดหมู่
    if category_slug:
        products = products.filter(category__slug=category_slug)

    # กรองตามคำค้นหาชื่อสินค้า
    if search_query:
        products = products.filter(name__icontains=search_query)

    # กรองตามราคาต่ำสุด (min_price)
    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass

    # กรองตามราคาสูงสุด (max_price)
    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass

    # ดึงสินค้าขายดี
    best_sellers = Product.objects.annotate(
        total_sold=Coalesce(Sum('orderitem__quantity'), Value(0))
    ).filter(is_best_seller=True)[:3]
    
    if not best_sellers.exists():
        best_sellers = Product.objects.annotate(
            total_sold=Coalesce(Sum('orderitem__quantity'), Value(0))
        ).order_by('-id')[:3]

    context = {
        'products': products,
        'categories': categories,
        'selected_category': category_slug,
        'search_query': search_query,
        'best_sellers': best_sellers,
    }
    return render(request, 'shop/product_list.html', context)

# 2. แสดงหน้ารายละเอียดสินค้าเฉพาะชิ้น
def product_detail(request, product_id):
  product = get_object_or_404(Product, id=product_id)
  return render(request, 'shop/product_detail.html', {'product': product})

# 3. เพิ่มสินค้าลงตะกร้า (บังคับล็อกอินก่อนและเช็คสต็อกหมด)
@login_required(login_url='login_view')
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = request.session.get('cart', {})

    selected_color = request.POST.get('color', 'ปกติ')
    
    # 1. รับค่าจำนวนที่ผู้ใช้กรอกเข้ามาจากฟอร์ม และป้องกันค่าติดลบ/ค่าว่าง
    try:
        quantity_to_add = int(request.POST.get('quantity', 1))
        if quantity_to_add < 1:
            quantity_to_add = 1
    except ValueError:
        quantity_to_add = 1

    cart_item_key = f'{product_id}_{selected_color}'

    # 2. ตรวจสอบสต็อกตามสีหรือสต็อกหลัก
    available_stock = 0
    try:
        p_color = ProductColor.objects.get(product=product, color_name=selected_color)
        available_stock = p_color.stock
    except ProductColor.DoesNotExist:
        available_stock = getattr(product, 'stock', 0)

    # 3. เช็คว่าสินค้าหมดหรือไม่
    if available_stock <= 0:
        messages.error(request, f'ขออภัย สินค้า "{product.name}" (สี: {selected_color}) หมดแล้วครับ')
        return redirect('product_detail', product_id=product.id)

    # 4. เช็คจำนวนในตะกร้าเดิม + จำนวนที่จะเพิ่มใหม่ ว่าเกินสต็อกหรือไม่
    current_qty_in_cart = cart.get(cart_item_key, {}).get('quantity', 0)
    
    if current_qty_in_cart + quantity_to_add > available_stock:
        messages.error(request, f'ไม่สามารถเพิ่มได้! สต็อกมีไม่พอ (คุณมีในตะกร้าแล้ว {current_qty_in_cart} ชิ้น, เหลือในสต็อก {available_stock} ชิ้น)')
        return redirect('product_detail', product_id=product.id)

    # 5. บันทึกข้อมูลลง Session ตะกร้าสินค้า
    if cart_item_key in cart:
        cart[cart_item_key]['quantity'] += quantity_to_add
    else:
        cart[cart_item_key] = {
            'product_id': product.id,
            'name': product.name,
            'price': float(product.price),
            'color': selected_color,
            'quantity': quantity_to_add,
            'image': product.image.url if product.image else '',
        }

    request.session['cart'] = cart
    messages.success(request, 'เพิ่มสินค้าลงตะกร้าสำเร็จ!')
    return redirect('product_detail', product_id=product.id)  # ✅ แก้ให้ดีดกลับมาหน้าเดิม

# 4. หน้าแสดงรายการในตะกร้า
def cart_detail(request):
  cart = request.session.get('cart', {})
  total_price = sum(
      item['price'] * item['quantity'] for item in cart.values()
  )
  return render(
      request, 'shop/cart.html', {'cart': cart, 'total_price': total_price}
  )


# 5. ลบสินค้าออกจากตะกร้า
def remove_from_cart(request, item_key):
  cart = request.session.get('cart', {})
  if item_key in cart:
    del cart[item_key]
    request.session['cart'] = cart
  return redirect('cart_detail')


# สมัครสมาชิก
def register_view(request):
  if request.method == 'POST':
    form = ThaiUserCreationForm(request.POST)
    if form.is_valid():
      user = form.save()
      login(request, user)
      return redirect('product_list')
  else:
    form = ThaiUserCreationForm()
  return render(request, 'shop/register.html', {'form': form})


# เข้าสู่ระบบ
def login_view(request):
  if request.method == 'POST':
    form = ThaiAuthenticationForm(request, data=request.POST)
    if form.is_valid():
      username = form.cleaned_data.get('username')
      password = form.cleaned_data.get('password')
      user = authenticate(username=username, password=password)
      if user is not None:
        login(request, user)
        return redirect('product_list')
  else:
    form = ThaiAuthenticationForm()
  return render(request, 'shop/login.html', {'form': form})


# 8. ออกจากระบบ
def logout_view(request):
  logout(request)
  return redirect('product_list')


# หน้ากรอกข้อมูลจัดส่งและยืนยันคำสั่งซื้อ
def checkout_view(request):
    cart = request.session.get('cart', {})
    if not cart:
        return redirect('cart_detail')

    total_price = sum(
        item['price'] * item['quantity'] for item in cart.values()
    )

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        address = request.POST.get('address')
        phone = request.POST.get('phone')

        # สร้าง Order ลงฐานข้อมูล
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            full_name=full_name,
            address=address,
            phone=phone,
            total_price=total_price,
        )

        # --- บันทึกรายการสินค้าลง OrderItem (รวมถึงสีที่เลือก) ---
        for item in cart.values():
            product = Product.objects.filter(id=item['product_id']).first()
            if product:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=item.get('name', product.name), # บันทึกชื่อสินค้า
                    color=item.get('color', 'ปกติ'),           # ✅ บันทึกชื่อสีลง Database ตรงนี้
                    quantity=item['quantity'],
                    price=item['price']
                )

        # --- 🛒 เคลียร์ตะกร้าสินค้าให้หายไปหลังสั่งซื้อสำเร็จ ---
        request.session['cart'] = {}
        request.session.modified = True

        # บันทึก Order ID ลงใน Session เพื่อใช้ต่อหน้าชำระเงิน
        request.session['order_id'] = order.id
        return redirect('/payment/')

    return render(request, 'shop/checkout.html', {'total_price': total_price})
# หน้าแสดง QR Code และอัปโหลดสลิป (พร้อมระบบตัดสต็อกอัตโนมัติ)
def payment_view(request):
    order_id = request.session.get('order_id')
    if not order_id:
        return redirect('product_list')

    order = get_object_or_404(Order, id=order_id)

    # 2. แปลงตัวคูณให้เป็น Decimal เพื่อให้คำนวณร่วมกับ total_price ได้
    subtotal = order.total_price  
    vat = subtotal * Decimal('0.07')         # ใช้ Decimal('0.07') แทน 0.07
    grand_total = subtotal + vat  

    if request.method == 'POST':
        if 'slip_image' in request.FILES:
            order.slip_image = request.FILES['slip_image']
            order.status = 'รอตรวจสอบสลิป'
            order.save()

            # ระบบตัดสต็อกตามสีที่สั่งซื้อ (ดึงจาก OrderItem ในฐานข้อมูล)
            for item in order.items.all(): 
                product = item.product
                selected_color = item.color
                quantity_bought = item.quantity

                try:
                    p_color = ProductColor.objects.get(
                        product=product, color_name=selected_color
                    )
                    if p_color.stock >= quantity_bought:
                        p_color.stock -= quantity_bought
                    else:
                        p_color.stock = 0
                    p_color.save()
                except ProductColor.DoesNotExist:
                    if product and hasattr(product, 'stock'):
                        if product.stock >= quantity_bought:
                            product.stock -= quantity_bought
                        else:
                            product.stock = 0
                        product.save()

            if 'order_id' in request.session:
                del request.session['order_id']

            return render(request, 'shop/payment_success.html', {'order': order})

    context = {
        'order': order,
        'subtotal': subtotal,
        'vat': vat,
        'grand_total': grand_total,
    }
    return render(request, 'shop/payment.html', context)

    # ส่งตัวแปรราคาและออเดอร์ไปแสดงผลที่หน้าชำระเงิน
    context = {
        'order': order,
        'subtotal': subtotal,
        'vat': vat,
        'grand_total': grand_total,
    }
    return render(request, 'shop/payment.html', context)

# ตัวอย่างการปรับแก้ในส่วน payment_view หรือฟังก์ชันยืนยันสลิปของแอดมิน
def admin_confirm_payment(request, order_id): # หรือฟังก์ชันที่คุณใช้เปลี่ยนสถานะออเดอร์
    order = get_object_or_404(Order, id=order_id)
    
    # สมมติว่าแอดมินกดเปลี่ยนสถานะเป็น 'ชำระเงินเรียบร้อย' / 'สำเร็จ'
    order.status = 'ชำระเงินสำเร็จ'
    order.save()

    # ดึงรายการสินค้าจาก Session หรือจากระบบตะกร้าตอนสั่งซื้อมาบันทึกเป็น OrderItem
    # (หากโปรเจกต์ของคุณบันทึกรายการสินค้าไว้เป็นตาราง OrderItem ตอนกด Checkout อยู่แล้ว ข้ามขั้นตอนนี้ได้เลยครับ)
    cart = request.session.get('cart', {})
    for item_key, item in cart.items():
        product = Product.objects.filter(id=item['product_id']).first()
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=item['name'],
            color=item['color'],
            quantity=item['quantity'],
            price=item['price']
        )
        
        # ตัดสต็อกตามสี
        try:
            p_color = ProductColor.objects.get(product_id=item['product_id'], color_name=item['color'])
            if p_color.stock >= item['quantity']:
                p_color.stock -= item['quantity']
            else:
                p_color.stock = 0
            p_color.save()
        except ProductColor.DoesNotExist:
            pass

    # เคลียร์ตะกร้าหลังยืนยันสำเร็จ (ถ้ามี)
    if 'cart' in request.session:
        del request.session['cart']

    return redirect('admin_dashboard')


# ฟังก์ชันสร้างและดาวน์โหลดใบเสร็จ PDF แบบแสดงรายการสินค้า
def download_receipt_pdf(request, order_id):
  order = get_object_or_404(Order, id=order_id)

  response = HttpResponse(content_type='application/pdf')
  response[
      'Content-Disposition'
  ] = f'attachment; filename="receipt_order_{order.id}.pdf"'

  p = canvas.Canvas(response, pagesize=letter)
  width, height = letter

  # ส่วนหัวใบเสร็จ
  p.setFont('Helvetica-Bold', 18)
  p.drawString(50, height - 50, 'SHOP RECEIPT')

  p.setFont('Helvetica', 11)
  p.drawString(50, height - 80, f'Order ID: #{order.id}')
  p.drawString(50, height - 100, f'Customer Name: {order.full_name}')
  p.drawString(50, height - 120, f'Phone: {order.phone}')
  p.drawString(50, height - 140, f'Address: {order.address}')

  # เส้นคั่นหัวข้อ
  p.setStrokeColor(colors.gray)
  p.line(50, height - 155, width - 50, height - 155)

  # หัวตารางรายการสินค้า
  p.setFont('Helvetica-Bold', 11)
  p.drawString(50, height - 180, 'Item Name / Description')
  p.drawString(320, height - 180, 'Qty')
  p.drawString(380, height - 180, 'Price')
  p.drawString(460, height - 180, 'Total')

  p.line(50, height - 190, width - 50, height - 190)

  # ดึงรายการสินค้าจาก Session
  cart = request.session.get('cart', {})
  y_position = height - 215
  p.setFont('Helvetica', 10)

  if cart:
    for item_key, item in cart.items():
      product_name = item.get('name', 'Product')
      color = item.get('color', '-')
      qty = item.get('quantity', 1)
      price = item.get('price', 0)
      item_total = price * qty

      p.drawString(50, y_position, f'{product_name} (Color: {color})')
      p.drawString(320, y_position, str(qty))
      p.drawString(380, y_position, f'{price:,.2f}')
      p.drawString(460, y_position, f'{item_total:,.2f}')

      y_position -= 25
  else:
    p.drawString(50, y_position, 'Order Total Items')
    p.drawString(460, y_position, f'{order.total_price:,.2f}')
    y_position -= 25

  p.setStrokeColor(colors.gray)
  y_position -= 10
  p.line(50, y_position, width - 50, y_position)

  # ยอดรวมสุทธิ
  y_position -= 30
  p.setFont('Helvetica-Bold', 12)
  p.drawString(350, y_position, 'Grand Total:')
  p.drawString(460, y_position, f'B {order.total_price:,.2f}')

  p.showPage()
  p.save()

  return response


@login_required(login_url='login_view')
def chat_room_view(request, user_id=None):
  # 1. ถ้าเป็นแอดมิน (Superuser)
  if request.user.is_superuser:
    customers = User.objects.filter(is_superuser=False)
    selected_customer = None
    messages = []
    if user_id:
      selected_customer = get_object_or_404(User, id=user_id)
      messages = ChatMessage.objects.filter(user=selected_customer).order_by(
          'created_at'
      )

    if request.method == 'POST':
      target_user_id = request.POST.get('target_user_id')
      target_user = get_object_or_404(User, id=target_user_id)
      message_text = request.POST.get('message', '')
      image_file = request.FILES.get('image', None)

      if message_text or image_file:
        ChatMessage.objects.create(
            user=target_user,
            message=message_text,
            image=image_file,
            is_admin_reply=True,
        )
        return redirect('chat_room_detail', user_id=target_user.id)

    return render(
        request,
        'shop/admin_chat.html',
        {
            'customers': customers,
            'selected_customer': selected_customer,
            'messages': messages,
        },
    )

  # 2. ถ้าเป็นลูกค้าทั่วไป ดูเฉพาะแชทของตัวเอง
  else:
    messages = ChatMessage.objects.filter(user=request.user).order_by(
        'created_at'
    )

    if request.method == 'POST':
      message_text = request.POST.get('message', '')
      image_file = request.FILES.get('image', None)

      if message_text or image_file:
        ChatMessage.objects.create(
            user=request.user,
            message=message_text,
            image=image_file,
            is_admin_reply=False,
        )
        return redirect('chat_room')

    return render(request, 'shop/chat.html', {'messages': messages})

def contact_view(request):
  return render(request, 'shop/contact.html')

@login_required(login_url='login_view')
def admin_statistics_view(request):
    if not request.user.is_superuser:
        return redirect('product_list')

    # 1. คำนวณรายรับรวมทั้งหมด (เฉพาะออเดอร์ที่ชำระเงินสำเร็จแล้ว)
    completed_orders = Order.objects.filter(status='ชำระเงินสำเร็จ') # ปรับชื่อสถานะตามจริงในระบบของคุณ
    total_revenue = completed_orders.aggregate(sum_price=Sum('total_price'))['sum_price'] or 0

    # 2. คำนวณสถิติสินค้าขายดี (จัดอันดับตามจำนวนที่ขายได้รวมกัน)
    best_sellers = (
        OrderItem.objects.filter(order__status='ชำระเงินสำเร็จ')
        .values('product_name', 'color')
        .annotate(total_sold=Sum('quantity'), total_income=Sum(F('price') * F('quantity')))
        .order_by('-total_sold')[:5] # ดึงมา 5 อันดับแรก
    )

    context = {
        'total_revenue': total_revenue,
        'completed_orders_count': completed_orders.count(),
        'best_sellers': best_sellers,
    }
    return render(request, 'shop/admin_statistics.html', context)

completed_orders = Order.objects.filter(status='ชำระเงินสำเร็จ') # สามารถปรับชื่อสถานะให้ตรงกับในฐานข้อมูลของคุณได้ เช่น 'รอตรวจสอบสลิป' หรือ 'สำเร็จแล้ว'

# คำนวณผลรวมยอดสั่งซื้อทั้งหมด
total_revenue = completed_orders.aggregate(sum_price=Sum('total_price'))['sum_price'] or 0

def home(request):
    # ดึงสินค้าเรียงตามยอดขายรวม (quantity) จากมากไปน้อย เอาแค่ 5 อันดับแรก
    # หมายเหตุ: 'orderitem__quantity' คือการดึงผ่าน Related Name จากโมเดล OrderItem
    best_sellers = Product.objects.annotate(
        total_sold=Sum('orderitem__quantity')
    ).filter(total_sold__gt=0).order_by('-total_sold')[:5]

    return render(request, 'shop/home.html', {
        'best_sellers': best_sellers
    })

@staff_member_required
def dashboard_view(request):
    orders = Order.objects.all()

    # รับค่าการกรองช่วงเวลา
    date_filter = request.GET.get('date_filter', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    today = timezone.now().date()

    if date_filter == 'today':
        orders = orders.filter(created_at__date=today)
    elif date_filter == '7days':
        orders = orders.filter(created_at__date__gte=today - timedelta(days=7))
    elif date_filter == 'month':
        orders = orders.filter(created_at__year=today.year, created_at__month=today.month)
    elif date_filter == 'year':
        orders = orders.filter(created_at__year=today.year)
    elif date_filter == 'custom' and start_date and end_date:
        orders = orders.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

    # 1. คำนวณยอดขายเฉพาะที่ตรวจสอบแล้ว (ชำระเงินสำเร็จ)
    verified_orders = orders.filter(status='ชำระเงินสำเร็จ')
    total_sales = verified_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0

    # 2. คำนวณยอดค้างชำระ / รอตรวจสอบ
    pending_orders = orders.exclude(status='ชำระเงินสำเร็จ')
    total_pending = pending_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0

    # 3. จำนวนคำสั่งซื้อทั้งหมด
    total_orders = orders.count()

    # 4. 🔥 คำนวณสินค้ายอดนิยม (เฉพาะออเดอร์ที่ตรวจสอบการชำระแล้วในช่วงเวลานั้น)
    best_sellers = (
        OrderItem.objects.filter(order__in=verified_orders)
        .values('product_name', 'color')
        .annotate(total_sold=Sum('quantity'), total_income=Sum(F('price') * F('quantity')))
        .order_by('-total_sold')[:5]  # ดึงมา 5 อันดับแรก
    )

    context = {
        'total_sales': total_sales,
        'total_pending': total_pending,
        'total_orders': total_orders,
        'orders': orders.order_by('-created_at')[:10],
        'best_sellers': best_sellers,  # ส่งตัวแปรนี้ไปแสดงผล
        'date_filter': date_filter,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'shop/dashboard.html', context)