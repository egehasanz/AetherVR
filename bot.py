import json
import time
import requests
import hashlib
import base64
import os
import sys
import ctypes
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import discord
from discord.ext import commands
import asyncio

CONFIG_FILE = "vr_users.json"
LOG_FILE = "bot_log.json"
CLIENT_ID = "1417273808645259344"

# Railway Environment Variables (Variables) üzerinden tokeni güvenle çeker
BOT_TOKEN = os.getenv("BOT_TOKEN")

REQUIRED_ROLE_ID = 1536136751565906013

# Botun açılış zamanını kaydetmek için
START_TIME = time.time()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def ekrani_gizle():
    """Siyah konsol ekranini gorunmez yapar (Windows tabanlı çalışmalarda)"""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

def log_yaz(mesaj, user_id=None):
    """Sistem olaylarini log.json dosyasına kaydeder"""
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except:
            logs = []
    
    log_entry = {
        "zaman": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": str(user_id) if user_id else "Sistem",
        "mesaj": mesaj
    }
    logs.append(log_entry)
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)

def load_db():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_db(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def generate_pkce():
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

class VRControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🥽 VR Bağlan / Güncelle", style=discord.ButtonStyle.success, custom_id="btn_vr_baglan_rol")
    async def vr_baglan_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Butona basan kullanıcının rol kontrolü
        user_roles = [role.id for role in interaction.user.roles]
        if REQUIRED_ROLE_ID not in user_roles:
            await interaction.response.send_message("❌ Bu işlemi gerçekleştirmek için gereken özel role sahip değilsin.", ephemeral=True)
            return

        code_verifier, code_challenge = generate_pkce()
        
        auth_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri=https://oculus.com/oauth_account_linking/login_redirect"
            f"&response_type=code"
            f"&scope=identify%20activities.read%20activities.write"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

        embed = discord.Embed(
            title="🥽 Meta Quest VR Yetkilendirme",
            description=(
                "1. Aşağıdaki **'Yetki Ver'** butonuna tıklayarak Discord hesabınla giriş yap.\n"
                "2. Karşına çıkacak (açılmayacak veya hata verecek olan oculus.com uzantılı) **tarayıcı adres çubuğundaki tüm URL'yi** kopyala.\n"
                "3. Kopyaladığın linki **buraya (özel mesaja) gönder**.\n\n"
                "⚠️ *Not: Bağlantı kurulduktan sonra durumun Discord'a yansıması 10-30 saniye sürebilir. Ayrıca bu durum genellikle **kendinizde görünmez**, ancak diğer kullanıcılar profilinizde görebilir.*"
            ),
            color=discord.Color.blue()
        )
        
        view_link = discord.ui.View()
        view_link.add_item(discord.ui.Button(label="🔗 Yetki Ver", url=auth_url, style=discord.ButtonStyle.link))

        await interaction.response.send_message(embed=embed, view=view_link, ephemeral=True)
        log_yaz("Kullanıcıya buton üzerinden OAuth yönergeleri gönderildi.", interaction.user.id)

        def check(m):
            return m.author == interaction.user and isinstance(m.channel, discord.DMChannel) and "code=" in m.content

        try:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send("📥 Kopyaladığın OAuth adresini buraya yapıştırıp gönder:")
            
            msg = await bot.wait_for('message', timeout=120.0, check=check)
            redirected_url = msg.content.strip()

            parsed = urlparse(redirected_url)
            code = parse_qs(parsed.query).get('code', [None])[0]
            if not code:
                raise ValueError()

            data = {
                "client_id": CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://oculus.com/oauth_account_linking/login_redirect",
                "code_verifier": code_verifier,
            }
            
            response = requests.post("https://discord.com/api/v10/oauth2/token", data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                db = load_db()
                
                db[str(interaction.user.id)] = {
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token", ""),
                    "status_name": "~~",
                    "session_token": None
                }
                save_db(db)
                
                success_embed = discord.Embed(
                    title="🎉 İşlem Başarılı!",
                    description=(
                        "Meta Quest VR durumun hesabına başarıyla bağlandı!\n\n"
                        "⏳ **10-30 saniye içinde** aktif olacaktır.\n"
                        "⚠️ *Bilgilendirme: Bu durum genellikle **kendinizde görünmez**, başkaları profilinize baktığında görebilir.*"
                    ),
                    color=discord.Color.green()
                )
                await dm_channel.send(embed=success_embed)
                log_yaz("Kullanıcı başarıyla bağlandı ve veritabanına kaydedildi.", interaction.user.id)
            else:
                await dm_channel.send("❌ Token alınamadı, işlem başarısız oldu. Lütfen tekrar dene.")
                log_yaz(f"Token alma hatası HTTP Kod: {response.status_code}", interaction.user.id)

        except Exception as e:
            try:
                await interaction.user.send("⏱️ Süre aşımı yaşandı veya bağlantı adresi hatalı formatta girildi.")
            except:
                pass
            log_yaz(f"Süre aşımı veya hata: {str(e)}", interaction.user.id)

    @discord.ui.button(label="🔌 Bağlantıyı Kes", style=discord.ButtonStyle.danger, custom_id="btn_vr_kes_rol")
    async def vr_kes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Bağlantı keserken de rol kontrolü isteğe bağlı yapılabilir ama genelde sadece db'de var mı diye bakılır
        user_roles = [role.id for role in interaction.user.roles]
        if REQUIRED_ROLE_ID not in user_roles:
            await interaction.response.send_message("❌ Bu işlemi gerçekleştirmek için gereken özel role sahip değilsin.", ephemeral=True)
            return

        db = load_db()
        user_id = str(interaction.user.id)
        
        if user_id in db:
            del db[user_id]
            save_db(db)
            
            embed = discord.Embed(
                title="🔌 Bağlantı Kesildi",
                description="VR durum bağlantın başarıyla sonlandırıldı ve veritabanından silindi.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log_yaz("Kullanıcı buton aracılığıyla bağlantısını kesti.", interaction.user.id)
        else:
            embed = discord.Embed(
                title="⚠️ Uyarı",
                description="Sistemde aktif bir VR bağlantın bulunmuyor.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user.name}")
    ekrani_gizle()
    bot.add_view(VRControlView())
    log_yaz("Bot başarıyla başlatıldı ve aktif hale geldi.")

@bot.command(name="vr")
async def vr_panel(ctx):
    # Komutu yazarken de rol kontrolü
    user_roles = [role.id for role in ctx.author.roles]
    if REQUIRED_ROLE_ID not in user_roles:
        embed = discord.Embed(
            title="⛔ Erişim Reddedildi",
            description="Bu komutu kullanmak için gereken özel role sahip değilsin.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title="🥽 Meta Quest VR Durum Yönetim Paneli",
        description="Aşağıdaki butonları kullanarak Meta Quest VR durumunu Discord hesabına bağlayabilir veya mevcut bağlantını sonlandırabilirsin.",
        color=discord.Color.blurple()
    )
    
    embed.set_footer(text="AetherVR Entegrasyon Altyapısı • Server Boost Özel Ayrıcalığı")
    
    view = VRControlView()
    await ctx.send(embed=embed, view=view)
    log_yaz("Kullanıcı için genel VR yönetim paneli açıldı.", ctx.author.id)

@bot.command(name="status")
async def bot_status(ctx):
    db = load_db()
    aktif_sayisi = len(db)
    
    embed = discord.Embed(
        title="📊 Sistem Durumu & İstatistikler",
        color=discord.Color.green()
    )
    embed.add_field(name="🥽 Aktif VR Kullanıcıları", value=f"```fix\n{aktif_sayisi} Kullanıcı bağlı\n```", inline=False)
    embed.add_field(name="🟢 Bot Durumu", value="```yaml\nÇalışıyor (Aktif)\n```", inline=True)
    embed.set_footer(text="AetherVR Entegrasyon Altyapısı")
    await ctx.send(embed=embed)

@bot.command(name="aktifler")
async def bot_aktifler(ctx):
    db = load_db()
    
    if not db:
        embed = discord.Embed(
            title="👥 Aktif VR Kullanıcıları",
            description="Şu anda sistemde bağlı aktif kullanıcı bulunmuyor.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return

    kullanici_listesi = []
    sayac = 1
    for user_id in db.keys():
        user = bot.get_user(int(user_id))
        if user:
            kullanici_listesi.append(f"{sayac}. 👤 **{user.name}** (Gizli ID)")
        else:
            kullanici_listesi.append(f"{sayac}. 👤 **Gizli Kullanıcı**")
        sayac += 1

    embed = discord.Embed(
        title="👥 Aktif VR Kullanıcı Listesi",
        description="Güvenlik nedeniyle kullanıcı ID'leri gizlenmiştir:\n\n" + "\n".join(kullanici_listesi),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Toplam: {len(db)} aktif kullanıcı • AetherVR")
    await ctx.send(embed=embed)

@bot.command(name="hosting")
async def bot_hosting(ctx):
    uptime_seconds = int(time.time() - START_TIME)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    uptime_str = f"{hours} saat, {minutes} dakika, {seconds} saniye"

    embed = discord.Embed(
        title="🖥️ Hosting & Sunucu Bilgileri",
        description="Botun barındırıldığı sistemin anlık teknik detayları:",
        color=discord.Color.purple()
    )
    embed.add_field(name="⚙️ İşletim Sistemi", value=f"```ansi\n\u001b[32mCloud / Railway Bulut\n```", inline=True)
    embed.add_field(name="🐍 Python Sürümü", value=f"```ansi\n\u001b[33m{sys.version.split()[0]}\n```", inline=True)
    embed.add_field(name="⏱️ Çalışma Süresi (Uptime)", value=f"```ansi\n\u001b[36m{uptime_str}\n```", inline=False)
    embed.add_field(name="📂 Veritabanı Türü", value="`JSON Tabanlı Yerel Veritabanı`", inline=True)
    embed.add_field(name="🏓 Gecikme (Latency)", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    
    embed.set_footer(text=f"Talep eden: {ctx.author.name} • AetherVR Hosting", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.event
async def setup_hook():
    bot.loop.create_task(background_status_updater())

async def background_status_updater():
    await bot.wait_until_ready()
    while not bot.is_closed():
        db = load_db()
        updated = False
        
        for user_id, user_data in list(db.items()):
            token = user_data.get("access_token", "").strip()
            session_token = user_data.get("session_token")
            
            if not token:
                continue
                
            activity = {
                "application_id": CLIENT_ID,
                "name": user_data.get("status_name", "~~"),
                "type": 6,
                "platform": "meta_quest"
            }
            try:
                response = requests.post(
                    "https://discord.com/api/v10/users/@me/headless-sessions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json={"activities": [activity], "token": session_token},
                    timeout=10
                )
                if response.status_code == 200:
                    new_session = response.json().get("token")
                    if new_session != session_token:
                        db[user_id]["session_token"] = new_session
                        updated = True
                elif response.status_code == 401:
                    del db[user_id]
                    updated = True
                    log_yaz("Geçersiz token tespit edildi, veritabanından kaldırıldı.", user_id)
            except:
                pass
                
        if updated:
            save_db(db)
            
        await asyncio.sleep(55)

if BOT_TOKEN:
    bot.run(BOT_TOKEN)
else:
    print("HATA: BOT_TOKEN çevresel değişkeni (Environment Variable) bulunamadı!")
