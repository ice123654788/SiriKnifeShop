from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django import forms
from django.core.exceptions import ValidationError

class RegisterForm(forms.ModelForm):
    # ตัวอย่างฟอร์มสมัครสมาชิก
    password = forms.CharField(
        widget=forms.PasswordInput,
        error_messages={
            'required': 'กรุณากรอกรหัสผ่าน'
        }
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        # เช็คความยาวรหัสผ่านน้อยกว่า 8 ตัวอักษร
        if len(password) < 8:
            raise forms.ValidationError("รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร")
            
        return password

class ThaiUserCreationForm(UserCreationForm):
    email = forms.EmailField(label="อีเมล", required=True, help_text="กรุณากรอกอีเมลที่ใช้งานจริง สำหรับกู้คืนรหัสผ่าน")

    class Meta:
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = "ชื่อผู้ใช้"
        self.fields['username'].help_text = "ตัวอักษร ตัวเลข และ @/./+/-/_ เท่านั้น (สูงสุด 150 ตัวอักษร)"
        self.fields['password1'].label = "รหัสผ่าน"
        self.fields['password1'].help_text = "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร"
        self.fields['password2'].label = "ยืนยันรหัสผ่าน"
        self.fields['password2'].help_text = "กรอกรหัสผ่านให้ตรงกันอีกครั้ง"

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            if len(password) < 8:
                raise ValidationError("รหัสผ่านสั้นเกินไป ต้องมีความยาวอย่างน้อย 8 ตัวอักษร")
            if password.isdigit():
                raise ValidationError("รหัสผ่านไม่ควรเป็นตัวเลขทั้งหมด")
        return password

class ThaiAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="ชื่อผู้ใช้หรืออีเมล", widget=forms.TextInput(attrs={'autofocus': True}))
    password = forms.CharField(label="รหัสผ่าน", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_messages = {
            'invalid_login': "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง",
            'inactive': "บัญชีนี้ถูกระงับการใช้งาน",
        }