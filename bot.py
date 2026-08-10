import discord
from discord.ext import commands, tasks
import json
import os
import requests
import hashlib
import base64
import random
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import psutil
import psycopg2
from urllib.parse import urlparse

# --- AYARLAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CLIENT_ID = "1417273808645259344"
GUILD_ID = 1515086899872796822
BOOST_ROLE_ID = 1536136751565906013
LOG_FILE = "log.json"

# --- POSTGRESQL VERİTABANI BAĞLANTISI ---
def get_db_connection():
    parsed_url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=parsed_url.path[1:],
        user=parsed_url.username,
        password=parsed_url.password,
        host=parsed_url.hostname,
        port=parsed_url.port
    )
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vr_users (
            discord_id TEXT PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# --- ÖZEL VR DURUM SEÇENEKLERİ ---
VR_ACTIVITIES = [
    "https://discord.gg/allahinaslanlari"
]

# --- LOG FONKSİYONU ---
def add_log(event_type, message):
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except:
            logs = []
    
    log_entry = {
        "zaman": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tur": event_type,
        "detay": message
    }
    
    logs.append(log_entry)
    if len(logs) > 500:
        logs = logs[-500:]
        
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents)

# PKCE Üretici
def generate_pkce():
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

VERIFIER_STORE = {}

class VRModal(discord.ui.Modal, title="Meta / Oculus Bağlantısı"):
    url_input = discord.ui.TextInput(
        label="Oculus Yönlendirme Linki",
        placeholder="https://www.oculus.com/oauth_account_linking/login_redirect?code=...",
        style=discord.TextStyle.long
    )

    def __init__(self, code_verifier):
        super().__init__()
        self.code_verifier = code_verifier

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        redirected_url = self.url_input.value.strip()

        try:
            parsed = urlparse(redirected_url)
            code = parse_qs(parsed.query).get('code', [None])[0]
            if not code:
                raise ValueError()
        except:
            add_log("HATA", f"Kullanıcı hatalı link girdi: {interaction.user} ({interaction.user.id})")
            await interaction.followup.send("❌ Hatalı link girdin, lütfen oculus.com ile başlayan tam adresi yapıştır.", ephemeral=True)
            return

        data = {
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://oculus.com/oauth_account_linking/login_redirect",
            "code_verifier": self.code_verifier,
        }
        
        response = requests.post("https://discord.com/api/v10/oauth2/token", data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token", "")
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO vr_users (discord_id, access_token, refresh_token)
                VALUES (%s, %s, %s)
                ON CONFLICT (discord_id) 
                DO UPDATE SET access_token = EXCLUDED.access_token, refresh_token = EXCLUDED.refresh_token
            """, (str(interaction.user.id), access_token, refresh_token))
            conn.commit()
            cur.close()
            conn.close()
            
            add_log("BASARILI", f"Kullanıcı VR hesabını bağladı: {interaction.user} ({interaction.user.id})")
            await interaction.followup.send("✅ **İşlem Başarılı!** VR durumun profilinde aktif edildi.", ephemeral=True)
        else:
            add_log("API_HATA", f"Discord/Meta token alınamadı. Kod: {response.status_code}, Yanıt: {response.text}, Kullanıcı: {interaction.user}")
            await interaction.followup.send(f"❌ Discord/Meta tarafında yetki alınamadı (Kod: {response.status_code}). Linkin süresi dolmuş olabilir.", ephemeral=True)

class VRView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔗 VR Hesabını Bağla", style=discord.ButtonStyle.green, custom_id="vr_pg_baglan_btn")
    async def baglan_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        
        if not member or not any(role.id == BOOST_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ Bu sistemi kullanabilmek için sunucumuza **Boost** basmış olman gerekiyor!", ephemeral=True)
            return

        code_verifier, code_challenge = generate_pkce()
        VERIFIER_STORE[interaction.user.id] = code_verifier

        auth_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri=https://oculus.com/oauth_account_linking/login_redirect"
            f"&response_type=code"
            f"&scope=identify"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

        embed = discord.Embed(
            title="🥽 Meta Quest Entegrasyon Adımları",
            description="Profilinde **Meta Quest** durumunu aktif etmek için aşağıdaki 3 basit adımı takip et:",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        embed.add_field(
            name="1️⃣ Yetkilendirme Sayfasına Git",
            value="Aşağıdaki **🌐 Meta ile Giriş Yap** butonuna tıklayarak tarayıcından onay ver.",
            inline=False
        )
        embed.add_field(
            name="2️⃣ Yönlendirme Linkini Kopyala",
            value="Giriş yaptıktan sonra yönlendirildiğin sayfanın adres çubuğundaki (`https://oculus.com/...`) adresi **tam olarak** kopyala.",
            inline=False
        )
        embed.add_field(
            name="3️⃣ Linki Sisteme İlet",
            value="**📝 Kopyaladığım Linki Gir** butonuna tıklayıp açılan kutucuğa kopyaladığın adresi yapıştır.",
            inline=False
        )
        embed.set_footer(text="🔒 Güvenli PostgreSQL Altyapısı • Verileriniz güvende.")

        class ActionView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.add_item(discord.ui.Button(label="🌐 Meta ile Giriş Yap", style=discord.ButtonStyle.link, url=auth_url))

            @discord.ui.button(label="📝 Kopyaladığım Linki Gir", style=discord.ButtonStyle.primary, custom_id="vr_pg_modal_btn")
            async def open_modal(self, inner_interaction: discord.Interaction, inner_button: discord.ui.Button):
                await inner_interaction.response.send_modal(VRModal(VERIFIER_STORE[inner_interaction.user.id]))

        await interaction.response.send_message(embed=embed, view=ActionView(), ephemeral=True)

    @discord.ui.button(label="🔌 Bağlantıyı Kes", style=discord.ButtonStyle.red, custom_id="vr_pg_kopar_btn")
    async def kopar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM vr_users WHERE discord_id = %s", (str(interaction.user.id),))
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()

        if deleted > 0:
            add_log("KOPARMA", f"Kullanıcı VR bağlantısını kesti: {interaction.user} ({interaction.user.id})")
            await interaction.response.send_message("🔌 VR entegrasyonu hesabından kaldırıldı.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Zaten aktif bir VR bağlantın bulunmuyor.", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"Bot aktif ve PostgreSQL bağlantısı hazır: {bot.user.name}")
    add_log("BILGI", f"Bot aktifleşti: {bot.user.name}")
    bot.add_view(VRView())
    vr_status_loop.start()

@bot.command()
@commands.has_permissions(administrator=True)
async def kurulumpanel(ctx):
    embed = discord.Embed(
        title="🥽 Meta Quest Profil Entegrasyon Merkezi",
        description=(
            "Sunucumuza **Boost** basarak profilinde **Meta Quest (VR)** aktivitesini aktif edebilirsin!\n\n"
            "✨ **Sistem Özellikleri:**\n"
            "• Profilinde otomatik değişen **Meta Quest** durumları görünür.\n"
            "• PostgreSQL güvencesiyle verileriniz kalıcı olarak saklanır.\n"
            "• İstediğin zaman tek tıkla bağlantını kesebilirsin.\n\n"
            "🚀 **Nasıl Aktif Edilir?**\n"
            "Aşağıdaki **🔗 VR Hesabını Bağla** butonuna tıklayarak adımları takip etmeniz yeterlidir."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )
    embed.set_footer(text="Meta Quest Entegrasyon Altyapısı • PostgreSQL")
    await ctx.send(embed=embed, view=VRView())
    await ctx.message.delete()
    add_log("PANEL", f"Kurulum paneli oluşturuldu: {ctx.channel.name} ({ctx.author})")

@bot.command()
@commands.has_permissions(administrator=True)
async def aktifler(ctx):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT discord_id FROM vr_users")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await ctx.send("❌ Sunucu bulunamadı.", delete_after=10)
        return

    aktif_kullanicilar = []
    for row in rows:
        member = guild.get_member(int(row[0]))
        if member:
            aktif_kullanicilar.append(f"• {member.mention} (`{member.name}`)")

    embed = discord.Embed(
        title="🥽 Aktif VR Entegrasyonu Bulunan Kullanıcılar",
        color=discord.Color.green()
    )

    if aktif_kullanicilar:
        embed.description = "\n".join(aktif_kullanicilar)
        embed.set_footer(text=f"Toplam Aktif Kullanıcı: {len(aktif_kullanicilar)}")
    else:
        embed.description = "Şu anda sistemde bağlı aktif bir kullanıcı bulunmuyor."

    await ctx.send(embed=embed)
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def status(ctx):
    process = psutil.Process(os.getpid())
    ram_usage = process.memory_info().rss / (1024 * 1024)
    system_ram = psutil.virtual_memory()
    cpu_usage = process.cpu_percent(interval=0.1)

    embed = discord.Embed(
        title="📊 Bot Sistem Durumu (Status)",
        color=discord.Color.blue()
    )
    embed.add_field(name="💻 Bot RAM Kullanımı", value=f"`{ram_usage:.2f} MB`", inline=True)
    embed.add_field(name="⚙️ Bot CPU Kullanımı", value=f"`%{cpu_usage}`", inline=True)
    embed.add_field(name="🖥️ Toplam Sunucu RAM", value=f"`%{system_ram.percent}` dolu ({system_ram.used // (1024*1024)}MB / {system_ram.total // (1024*1024)}MB)", inline=False)
    embed.set_footer(text="Railway / PostgreSQL Altyapısı")
    
    await ctx.send(embed=embed)
    await ctx.message.delete()

@tasks.loop(seconds=55)
async def vr_status_loop():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT discord_id, access_token FROM vr_users")
    rows = cur.fetchall()
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        cur.close()
        conn.close()
        return

    silinecekler = []
    for discord_id, access_token in rows:
        member = guild.get_member(int(discord_id))
        
        if not member or not any(role.id == BOOST_ROLE_ID for role in member.roles):
            silinecekler.append(discord_id)
            add_log("SILINME", f"Kullanıcı sunucudan çıktı veya boost'u bitti, veritabanından silindi: {discord_id}")
            continue

        chosen_activity_name = random.choice(VR_ACTIVITIES)

        activity = {
            "application_id": CLIENT_ID,
            "name": chosen_activity_name,
            "type": 0,
            "platform": "meta_quest"
        }

        try:
            response = requests.post(
                "https://discord.com/api/v10/users/@me/headless-sessions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json={"activities": [activity]},
                timeout=10
            )
            if response.status_code == 401:
                silinecekler.append(discord_id)
                add_log("TOKEN_GECERSIZ", f"Token süresi dolmuş, kullanıcı silindi: {discord_id}")
        except Exception as e:
            pass

    if silinecekler:
        cur.executemany("DELETE FROM vr_users WHERE discord_id = %s", [(uid,) for uid in silinecekler])
        conn.commit()

    cur.close()
    conn.close()

bot.run(BOT_TOKEN)
