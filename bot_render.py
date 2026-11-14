import discord
from discord import app_commands
from discord.ext import commands
import datetime

# ================= НАСТРОЙКИ =================
TOKEN = ""
GUILD_ID = 1549118999663747173          # ID твоего сервера
LOG_CHANNEL_ID = 1570373538911625288    # ID канала для логов
VERIFIED_ROLE_ID = None  # ID роли "Верифицирован"
UNVERIFIED_ROLE_ID = 1570372987201265734  # ID роли "Неверифицирован" (если есть)

# ID гендерных ролей на сервере (замени на реальные ID)
GENDER_ROLES = {
    "male": 1570373001231343699,    # ID роли "Мужской" / "Мужской пол"
    "female": 1570373002418196500,  # ID роли "Женский" / "Женский пол"
}

# Словарь иерархии стафф-должностей по направлениям
ROLE_MAPPING = {
    "support": {
        "master": 1570372942800359495,
        "curator": 1570372941772881962,
        "head_curator": 1570372940569120828,
    },
    "moderation": {
        "master": 0,
        "curator": 0,
        "head_curator": 0,
    },
    "event": {"master": 0, "curator": 0, "head_curator": 0},
    "close": {"master": 0, "curator": 0, "head_curator": 0},
    "tribune": {"master": 0, "curator": 0, "head_curator": 0},
    "creative": {"master": 0, "curator": 0, "head_curator": 0},
    "content": {"master": 0, "curator": 0, "head_curator": 0},
}
# =============================================

intents = discord.Intents.default()
intents.members = True

class DaarToolsBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = DaarToolsBot()

async def send_log(guild: discord.Guild, title: str, moderator: discord.Member, target: discord.Member, details: str, color: discord.Color):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return
    embed = discord.Embed(title=f"🛡️ DaarTools | {title}", color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="Модератор", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
    embed.add_field(name="Участник", value=f"{target.mention} (`{target.id}`)", inline=True)
    embed.add_field(name="Подробности", value=details, inline=False)
    await log_channel.send(embed=embed)

# ================= МОДАЛЬНЫЕ ОКНА (БАН, МУТ, ВАРН) =================

class ReasonModal(discord.ui.Modal):
    def __init__(self, action_type: str, target: discord.Member):
        titles = {"ban": f"Бан: {target.display_name}", "mute": f"Мут: {target.display_name}", "warn": f"Предупреждение: {target.display_name}"}
        super().__init__(title=titles[action_type])
        self.action_type = action_type
        self.target = target

        if action_type == "mute":
            self.duration = discord.ui.TextInput(label="Длительность (в минутах)", placeholder="60", required=True, max_length=5)
            self.add_item(self.duration)

        self.reason = discord.ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, placeholder="Укажите причину...", required=True, max_length=500)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.reason.value
        guild = interaction.guild
        try:
            if self.action_type == "ban":
                await self.target.ban(reason=f"[{interaction.user}] {reason_text}")
                await send_log(guild, "Бан участника", interaction.user, self.target, f"**Причина:** {reason_text}", discord.Color.red())
                await interaction.response.send_message(f"🚫 Пользователь {self.target.mention} забанен.", ephemeral=True)
            elif self.action_type == "mute":
                minutes = int(self.duration.value)
                until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
                await self.target.timeout(until, reason=f"[{interaction.user}] {reason_text}")
                await send_log(guild, "Мут (тайм-аут)", interaction.user, self.target, f"**Время:** {minutes} мин.\n**Причина:** {reason_text}", discord.Color.orange())
                await interaction.response.send_message(f"⏳ Мут выдан {self.target.mention} на {minutes} мин.", ephemeral=True)
            elif self.action_type == "warn":
                try:
                    await self.target.send(f"⚠️ Предупреждение на сервере **{guild.name}**.\n**Причина:** {reason_text}")
                except discord.Forbidden:
                    pass
                await send_log(guild, "Предупреждение", interaction.user, self.target, f"**Причина:** {reason_text}", discord.Color.gold())
                await interaction.response.send_message(f"⚠️ Предупреждение выдано {self.target.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка выполнения: {e}", ephemeral=True)

# ================= УПРАВЛЕНИЕ ГЕНДЕРНЫМИ РОЛЯМИ (АВТОМАТИЧЕСКАЯ ЗАМЕНА) =================

class GenderSelectView(discord.ui.View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=180)
        self.target = target

    @discord.ui.select(
        placeholder="Выберите гендерную роль для выдачи...",
        options=[
            discord.SelectOption(label="Мужской", value="male", description="Выдать мужскую роль (старая женская снимется)", emoji="👦"),
            discord.SelectOption(label="Женский", value="female", description="Выдать женскую роль (старая мужская снимется)", emoji="👧"),
        ]
    )
    async def select_gender(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_key = select.values[0]
        guild = interaction.guild

        role_to_add_id = GENDER_ROLES.get(selected_key)
        role_to_add = guild.get_role(role_to_add_id)

        if not role_to_add:
            await interaction.response.edit_message(content="❌ Ошибка: выбранная роль не найдена на сервере (проверь GENDER_ROLES).", view=None)
            return

        # Определяем вторую роль, которую нужно забрать (если она есть)
        other_key = "female" if selected_key == "male" else "male"
        role_to_remove_id = GENDER_ROLES.get(other_key)
        role_to_remove = guild.get_role(role_to_remove_id)

        try:
            removed_text = ""
            # Если у пользователя уже была противоположная роль — забираем её
            if role_to_remove and role_to_remove in self.target.roles:
                await self.target.remove_roles(role_to_remove, reason=f"Замена гендерки через DaarTools ({interaction.user})")
                removed_text = f" (удалена старая роль: {role_to_remove.mention})"

            # Выдаем новую роль
            await self.target.add_roles(role_to_add, reason=f"Выдано через DaarTools ({interaction.user})")
            
            # Логируем действие
            await send_log(
                guild, 
                "Смена гендерки", 
                interaction.user, 
                self.target, 
                f"**Выдано:** {role_to_add.mention}{removed_text}", 
                discord.Color.teal()
            )

            await interaction.response.edit_message(content=f"✅ Участнику {self.target.mention} успешно установлена роль {role_to_add.mention}{removed_text}!", view=None)

        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ Ошибка прав! Роль бота должна быть выше гендерных ролей в списке ролей Discord.", view=None)

# ================= МЕНЮ ВЫДАЧИ ДОЛЖНОСТЕЙ =================

class RankSelectView(discord.ui.View):
    def __init__(self, target: discord.Member, direction: str):
        super().__init__(timeout=180)
        self.target = target
        self.direction = direction

    @discord.ui.select(
        placeholder="Выберите должность в иерархии...",
        options=[
            discord.SelectOption(label="Мастер", value="master", description="Руководит сотрудниками своей ветки", emoji="📌"),
            discord.SelectOption(label="Куратор", value="curator", description="Отвечает за мастеров", emoji="⭐"),
            discord.SelectOption(label="Главный куратор", value="head_curator", description="Отвечает за кураторов", emoji="👑"),
        ]
    )
    async def select_rank(self, interaction: discord.Interaction, select: discord.ui.Select):
        rank_key = select.values[0]
        role_id = ROLE_MAPPING.get(self.direction, {}).get(rank_key)

        if not role_id:
            await interaction.response.edit_message(content="❌ Роль для этой должности еще не настроена в коде (ROLE_MAPPING).", view=None)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.edit_message(content="❌ Роль с таким ID не найдена на сервере.", view=None)
            return

        try:
            await self.target.add_roles(role, reason=f"Выдано через DaarTools ({interaction.user})")
            await send_log(interaction.guild, "Выдача должности", interaction.user, self.target, f"**Направление:** {self.direction}\n**Должность:** {role.mention}", discord.Color.blurple())
            await interaction.response.edit_message(content=f"✅ Участнику {self.target.mention} успешно выдана должность {role.mention}!", view=None)
        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ Ошибка прав: роль бота должна быть выше выдаваемой роли.", view=None)

class DirectionSelectView(discord.ui.View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=180)
        self.target = target

    @discord.ui.select(
        placeholder="Выберите направление (ветку)...",
        options=[
            discord.SelectOption(label="Саппорт", value="support", emoji="🎧"),
            discord.SelectOption(label="Модерация", value="moderation", emoji="🛡️"),
            discord.SelectOption(label="Ивент-модерация", value="event", emoji="📅"),
            discord.SelectOption(label="Клоуз-модерация", value="close", emoji="🔒"),
            discord.SelectOption(label="Трибун-модерация", value="tribune", emoji="🎤"),
            discord.SelectOption(label="Креатив", value="creative", emoji="🎨"),
            discord.SelectOption(label="Контент-мейкер", value="content", emoji="📹"),
        ]
    )
    async def select_direction(self, interaction: discord.Interaction, select: discord.ui.Select):
        direction = select.values[0]
        await interaction.response.edit_message(
            content=f"Выбран участник: {self.target.mention}\nНаправление: **{select.values[0]}**\nТеперь выберите должность:", 
            view=RankSelectView(self.target, direction)
        )

class RoleSelectGeneric(discord.ui.RoleSelect):
    def __init__(self, mode: str, target: discord.Member):
        super().__init__(placeholder="Выберите роль из списка...", min_values=1, max_values=1)
        self.mode = mode
        self.target = target

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        try:
            if self.mode == "add":
                await self.target.add_roles(role, reason=f"Выдано через DaarTools ({interaction.user})")
                await send_log(interaction.guild, "Выдача роли", interaction.user, self.target, f"**Роль:** {role.mention}", discord.Color.blurple())
                await interaction.response.edit_message(content=f"✅ Роль {role.mention} выдана участнику {self.target.mention}.", view=None)
            else:
                await self.target.remove_roles(role, reason=f"Снято через DaarTools ({interaction.user})")
                await send_log(interaction.guild, "Снятие роли", interaction.user, self.target, f"**Роль:** {role.mention}", discord.Color.dark_grey())
                await interaction.response.edit_message(content=f"✅ Роль {role.mention} снята с участника {self.target.mention}.", view=None)
        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ Ошибка прав бота.", view=None)

class UserSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        super().__init__(placeholder="Выберите участника сервера...", min_values=1, max_values=1)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        if not isinstance(target, discord.Member):
            await interaction.response.send_message("❌ Участник не найден на сервере.", ephemeral=True)
            return

        if self.action == "verify":
            v_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
            if not v_role:
                await interaction.response.edit_message(content="❌ Роль верификации не настроена.", view=None)
                return
            try:
                await target.add_roles(v_role, reason=f"Верифицирован {interaction.user}")
                if UNVERIFIED_ROLE_ID:
                    unv_role = interaction.guild.get_role(UNVERIFIED_ROLE_ID)
                    if unv_role and unv_role in target.roles:
                        await target.remove_roles(unv_role)
                await send_log(interaction.guild, "Ручная верификация", interaction.user, target, f"Выдана роль {v_role.mention}", discord.Color.green())
                await interaction.response.edit_message(content=f"🛡️ Участник {target.mention} успешно верифицирован!", view=None)
            except discord.Forbidden:
                await interaction.response.edit_message(content="❌ Ошибка прав бота.", view=None)

        elif self.action == "gender":
            # Открываем меню выбора гендерки с автоматической заменой
            await interaction.response.edit_message(content=f"Выбран участник: {target.mention}\nВыберите гендерную роль:", view=GenderSelectView(target))

        elif self.action == "staff_role":
            await interaction.response.edit_message(content=f"Выбран участник: {target.mention}\nВыберите направление стаффа:", view=DirectionSelectView(target))

        elif self.action == "remove_role":
            view = discord.ui.View()
            view.add_item(RoleSelectGeneric("remove", target))
            await interaction.response.edit_message(content=f"Участник: {target.mention}. Выберите роль для снятия:", view=view)

        elif self.action in ("ban", "mute", "warn"):
            await interaction.response.send_modal(ReasonModal(self.action, target))

# ================= ГЛАВНАЯ ПАНЕЛЬ /action =================

class ActionPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    async def prompt_user(self, interaction: discord.Interaction, action: str, text: str):
        view = discord.ui.View()
        view.add_item(UserSelect(action))
        await interaction.response.send_message(text, view=view, ephemeral=True)

    @discord.ui.button(label="Верифицировать", style=discord.ButtonStyle.secondary, emoji="🛡️", row=0)
    async def verify_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "verify", "🛡️ Кого нужно верифицировать?")

    @discord.ui.button(label="Выдать гендерку", style=discord.ButtonStyle.secondary, emoji="🚻", row=0)
    async def gender_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "gender", "🚻 Кому изменить/выдать гендерную роль?")

    @discord.ui.button(label="Выдать должность", style=discord.ButtonStyle.secondary, emoji="➕", row=0)
    async def add_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "staff_role", "➕ Кому выдать стафф-должность?")

    @discord.ui.button(label="Снять роль", style=discord.ButtonStyle.secondary, emoji="➖", row=1)
    async def remove_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "remove_role", "➖ У кого снять роль?")

    @discord.ui.button(label="Бан", style=discord.ButtonStyle.danger, emoji="🚫", row=1)
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "ban", "🚫 Кого заблокировать?")

    @discord.ui.button(label="Мут", style=discord.ButtonStyle.secondary, emoji="🕒", row=2)
    async def mute_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "mute", "🕒 Кому выдать мут?")

    @discord.ui.button(label="Предупреждение", style=discord.ButtonStyle.secondary, emoji="⚠️", row=2)
    async def warn_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_user(interaction, "warn", "⚠️ Кому выдать предупреждение?")

@bot.tree.command(name="action", description="Открыть панель модерации DaarTools")
@app_commands.default_permissions(administrator=True)
async def action_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="DaarTools",
        description="MODERATION SYSTEM & MANAGEMENT\n\n**Выбери необходимое действие:**",
        color=0x9B87F5
    )
    embed.set_footer(text="Панель управления DaarTools")
    await interaction.response.send_message(embed=embed, view=ActionPanelView(), ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} запущен и готов к работе!")

if __name__ == "__main__":
    bot.run(TOKEN)