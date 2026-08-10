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

# --- AYARLAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = "1417273808645259344"
GUILD_ID = 1515086899872796822
BOOST_ROLE_ID = 1536136751565906013
DB_FILE = "veritabani.json"
LOG_FILE = "log.json"

# --- Ã–ZEL VR DURUM SEÃ‡ENEKLERÄ° ---
VR_ACTIVITIES = [
    "Meta Quest VR ile oynuyor",
    "Quest OS Ana MenÃ¼de",
    "VRChat dÃ¼nyalarÄ±nÄ± geziyor",
    "https://discord.gg/allahinaslanlari"
]

# --- LOG FONKSÄ°YONU ---
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

# --- JSON VERÄ°TABANI YÃ–NETÄ°CÄ°SÄ° ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents)

# PKCE Ãœretici
def generate_pkce():
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

VERIFIER_STORE = {}

class VRModal(discord.ui.Modal, title="Meta / Oculus BaÄŸlantÄ±sÄ±"):
    url_input = discord.ui.TextInput(
        label="Oculus YÃ¶nlendirme Linki",
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
            add_log("HATA", f"KullanÄ±cÄ± hatalÄ± link girdi: {interaction.user} ({interaction.user.id})")
            await interaction.followup.send("âŒ HatalÄ± link girdin, lÃ¼tfen oculus.com ile baÅŸlayan tam adresi yapÄ±ÅŸtÄ±r.", ephemeral=True)
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
            
            db = load_db()
            db[str(interaction.user.id)] = {
                "access_token": access_token,
                "refresh_token": refresh_token
            }
            save_db(db)
            
            add_log("BASARILI", f"KullanÄ±cÄ± VR hesabÄ±nÄ± baÄŸladÄ±: {interaction.user} ({interaction.user.id})")
            await interaction.followup.send("âœ… **Ä°ÅŸlem BaÅŸarÄ±lÄ±!** VR durumun profilinde aktif edildi.", ephemeral=True)
        else:
            add_log("API_HATA", f"Discord/Meta token alÄ±namadÄ±. Kod: {response.status_code}, KullanÄ±cÄ±: {interaction.user}")
            await interaction.followup.send("âŒ Discord/Meta tarafÄ±nda yetki alÄ±namadÄ±. Linkin sÃ¼resi dolmuÅŸ olabilir, tekrar dene.", ephemeral=True)

class VRView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ğŸ”— VR HesabÄ±nÄ± BaÄŸla", style=discord.ButtonStyle.green, custom_id="vr_baglan_btn")
    async def baglan_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        
        if not member or not any(role.id == BOOST_ROLE_ID for role in member.roles):
            await interaction.response.send_message("âŒ Bu sistemi kullanabilmek iÃ§in sunucumuza **Boost** basmÄ±ÅŸ olman gerekiyor!", ephemeral=True)
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
            title="ğŸ¥½ Meta Quest Entegrasyon AdÄ±mlarÄ±",
            description="Profilinde **Meta Quest** durumunu aktif etmek iÃ§in aÅŸaÄŸÄ±daki 3 basit adÄ±mÄ± takip et:",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        embed.add_field(
            name="1ï¸âƒ£ Yetkilendirme SayfasÄ±na Git",
            value="AÅŸaÄŸÄ±daki **ğŸŒ Meta ile GiriÅŸ Yap** butonuna tÄ±klayarak tarayÄ±cÄ±ndan onay ver.",
            inline=False
        )
        embed.add_field(
            name="2ï¸âƒ£ YÃ¶nlendirme Linkini Kopyala",
            value="GiriÅŸ yaptÄ±ktan sonra yÃ¶nlendirildiÄŸin sayfanÄ±n adres Ã§ubuÄŸundaki (`https://oculus.com/...`) adresi **tam olarak** kopyala.",
            inline=False
        )
        embed.add_field(
            name="3ï¸âƒ£ Linki Sisteme Ä°let",
            value="**ğŸ“ KopyaladÄ±ÄŸÄ±m Linki Gir** butonuna tÄ±klayÄ±p aÃ§Ä±lan kutucuÄŸa kopyaladÄ±ÄŸÄ±n adresi yapÄ±ÅŸtÄ±r.",
            inline=False
        )
        embed.set_footer(text="ğŸ”’ GÃ¼venli OAuth2 AltyapÄ±sÄ± â€¢ Verileriniz ÅŸifrelenerek korunmaktadÄ±r.")

        class ActionView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.add_item(discord.ui.Button(label="ğŸŒ Meta ile GiriÅŸ Yap", style=discord.ButtonStyle.link, url=auth_url))

            @discord.ui.button(label="ğŸ“ KopyaladÄ±ÄŸÄ±m Linki Gir", style=discord.ButtonStyle.primary, custom_id="modal_trigger_btn")
            async def open_modal(self, inner_interaction: discord.Interaction, inner_button: discord.ui.Button):
                await inner_interaction.response.send_modal(VRModal(VERIFIER_STORE[inner_interaction.user.id]))

        await interaction.response.send_message(embed=embed, view=ActionView(), ephemeral=True)

    @discord.ui.button(label="ğŸ”Œ BaÄŸlantÄ±yÄ± Kes", style=discord.ButtonStyle.red, custom_id="vr_kopar_btn")
    async def kopar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_db()
        user_id_str = str(interaction.user.id)
        if user_id_str in db:
            del db[user_id_str]
            save_db(db)
            add_log("KOPARMA", f"KullanÄ±cÄ± VR baÄŸlantÄ±sÄ±nÄ± kesti: {interaction.user} ({interaction.user.id})")
            await interaction.response.send_message("ğŸ”Œ VR entegrasyonu hesabÄ±ndan kaldÄ±rÄ±ldÄ±.", ephemeral=True)
        else:
            await interaction.response.send_message("âŒ Zaten aktif bir VR baÄŸlantÄ±n bulunmuyor.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user.name}")
    add_log("BILGI", f"Bot aktifleÅŸti: {bot.user.name}")
    bot.add_view(VRView())
    vr_status_loop.start()

@bot.command()
@commands.has_permissions(administrator=True)
async def kurulumpanel(ctx):
    embed = discord.Embed(
        title="ğŸ¥½ Meta Quest Profil Entegrasyon Merkezi",
        description=(
            "Sunucumuza **Boost** basarak profilinde **Meta Quest (VR)** aktivitesini aktif edebilirsin!\n\n"
            "âœ¨ **Sistem Ã–zellikleri:**\n"
            "â€¢ Profilinde otomatik deÄŸiÅŸen **Meta Quest** durumlarÄ± gÃ¶rÃ¼nÃ¼r.\n"
            "â€¢ HesabÄ±n kesintisiz olarak 7/24 arka planda gÃ¼ncellenir.\n"
            "â€¢ Ä°stediÄŸin zaman tek tÄ±kla baÄŸlantÄ±nÄ± kesebilirsin.\n\n"
            "ğŸš€ **NasÄ±l Aktif Edilir?**\n"
            "AÅŸaÄŸÄ±daki **ğŸ”— VR HesabÄ±nÄ± BaÄŸla** butonuna tÄ±klayarak adÄ±mlarÄ± takip etmeniz yeterlidir."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )
    embed.set_footer(text="Meta Quest Entegrasyon AltyapÄ±sÄ± â€¢ Server Boost Ã–zel AyrÄ±calÄ±ÄŸÄ±")
    await ctx.send(embed=embed, view=VRView())
    await ctx.message.delete()
    add_log("PANEL", f"Kurulum paneli oluÅŸturuldu: {ctx.channel.name} ({ctx.author})")

@bot.command()
@commands.has_permissions(administrator=True)
async def aktifler(ctx):
    db = load_db()
    guild = bot.get_guild(GUILD_ID)
    
    if not guild:
        await ctx.send("âŒ Sunucu bulunamadÄ±.", delete_after=10)
        return

    aktif_kullanicilar = []
    for discord_id in db.keys():
        member = guild.get_member(int(discord_id))
        if member:
            aktif_kullanicilar.append(f"â€¢ {member.mention} (`{member.name}`)")

    embed = discord.Embed(
        title="ğŸ¥½ Aktif VR Entegrasyonu Bulunan KullanÄ±cÄ±lar",
        color=discord.Color.green()
    )

    if aktif_kullanicilar:
        embed.description = "\n".join(aktif_kullanicilar)
        embed.set_footer(text=f"Toplam Aktif KullanÄ±cÄ±: {len(aktif_kullanicilar)}")
    else:
        embed.description = "Åu anda sistemde baÄŸlÄ± aktif bir kullanÄ±cÄ± bulunmuyor."

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
        title="ğŸ“Š Bot Sistem Durumu (Status)",
        color=discord.Color.blue()
    )
    embed.add_field(name="ğŸ’» Bot RAM KullanÄ±mÄ±", value=f"`{ram_usage:.2f} MB`", inline=True)
    embed.add_field(name="âš™ï¸ Bot CPU KullanÄ±mÄ±", value=f"`%{cpu_usage}`", inline=True)
    embed.add_field(name="ğŸ–¥ï¸ Toplam Sunucu RAM", value=f"`%{system_ram.percent}` dolu ({system_ram.used // (1024*1024)}MB / {system_ram.total // (1024*1024)}MB)", inline=False)
    embed.set_footer(text="Railway / Sunucu AltyapÄ±sÄ±")
    
    await ctx.send(embed=embed)
    await ctx.message.delete()

@tasks.loop(seconds=55)
async def vr_status_loop():
    db = load_db()
    if not db:
        return
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    updated = False
    for discord_id, user_data in list(db.items()):
        member = guild.get_member(int(discord_id))
        
        if not member or not any(role.id == BOOST_ROLE_ID for role in member.roles):
            del db[discord_id]
            updated = True
            add_log("SILINME", f"KullanÄ±cÄ± sunucudan Ã§Ä±ktÄ± veya boost'u bitti, veritabanÄ±ndan silindi: {discord_id}")
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
                    "Authorization": f"Bearer {user_data['access_token']}"
                },
                json={"activities": [activity]},
                timeout=10
            )
            if response.status_code == 401:
                del db[discord_id]
                updated = True
                add_log("TOKEN_GECERSIZ", f"Token sÃ¼resi dolmuÅŸ, kullanÄ±cÄ± silindi: {discord_id}")
        except Exception as e:
            pass

    if updated:
        save_db(db)

bot.run(BOT_TOKEN)