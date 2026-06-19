import os
import discord
from discord.ext import commands
from discord.ui import View, Modal, TextInput, Button
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ORDER_CHANNEL_ID = int(os.getenv("ORDER_CHANNEL_ID"))
PAYMENT_CHANNEL_ID = int(os.getenv("PAYMENT_CHANNEL_ID"))
REVIEW_CHANNEL_ID = 1517663406373474364

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_orders = {}
pending_reviews = {}


# -----------------------------
# REVIEW MODAL
# -----------------------------
class ReviewModal(Modal, title="Leave a Review"):
    stars = TextInput(label="How many stars? (1-5)", required=True)
    reason = TextInput(label="Why?", required=True, style=discord.TextStyle.paragraph)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = int(self.stars.value)
            if stars < 1 or stars > 5:
                raise ValueError()
        except:
            return await interaction.response.send_message(
                "❌ Stars must be 1–5.",
                ephemeral=True
            )

        review_channel = bot.get_channel(REVIEW_CHANNEL_ID) or await bot.fetch_channel(REVIEW_CHANNEL_ID)

        embed = discord.Embed(
            title="⭐ New Review",
            color=discord.Color.gold()
        )

        embed.add_field(name="User", value=interaction.user.mention, inline=False)
        embed.add_field(name="Stars", value=f"{stars}/5", inline=True)
        embed.add_field(name="Reason", value=self.reason.value, inline=False)

        await review_channel.send(embed=embed)

        pending_reviews.pop(self.user_id, None)

        await interaction.response.send_message(
            "✅ Thanks for your review!",
            ephemeral=True
        )


# -----------------------------
# REVIEW BUTTON
# -----------------------------
class ReviewView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(
        label="Make Review",
        style=discord.ButtonStyle.primary,
        emoji="⭐"
    )
    async def review(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This is not your review prompt.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            ReviewModal(self.user_id)
        )


# -----------------------------
# COLLECT BUTTON (DM)
# -----------------------------
class CollectView(View):
    def __init__(self, message_id: int, user_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.user_id = user_id

    @discord.ui.button(
        label="Collected",
        style=discord.ButtonStyle.success,
        emoji="📦"
    )
    async def collected(self, interaction: discord.Interaction, button: Button):

        order = active_orders.get(self.message_id)
        if not order:
            return await interaction.response.send_message("Order not found.", ephemeral=True)

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your order.", ephemeral=True)

        pending_reviews[self.user_id] = True

        await interaction.response.send_message(
            "📩 Send a review?",
            view=ReviewView(self.user_id),
            ephemeral=True
        )


# -----------------------------
# STAFF VIEW
# -----------------------------
class StaffView(View):
    def __init__(self, user_id: int, code: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.code = code

    # PAYMENT
    @discord.ui.button(label="Needs Payment", style=discord.ButtonStyle.primary, emoji="💳")
    async def payment(self, interaction: discord.Interaction, button: Button):

        channel = bot.get_channel(PAYMENT_CHANNEL_ID) or await bot.fetch_channel(PAYMENT_CHANNEL_ID)
        customer = await bot.fetch_user(self.user_id)

        thread = await channel.create_thread(
            name=f"payment-{customer.name}",
            type=discord.ChannelType.private_thread
        )

        await thread.add_user(interaction.user)
        member = interaction.guild.get_member(self.user_id)
        if member:
            await thread.add_user(member)

        await thread.send(
            f"💳 Payment required\n"
            f"{customer.mention} | Staff: {interaction.user.mention}"
        )

        await interaction.response.send_message(
            f"Thread created: {thread.mention}",
            ephemeral=True
        )

    # READY
    @discord.ui.button(label="Ready To Collect", style=discord.ButtonStyle.green, emoji="📦")
    async def ready(self, interaction: discord.Interaction, button: Button):

        user = await bot.fetch_user(self.user_id)

        dm = await user.send(
            f"🟢 Ready for collection\n\nCode: **{self.code}**"
        )

        view = CollectView(dm.id, self.user_id)
        await dm.edit(view=view)

        await interaction.response.send_message("DM sent.", ephemeral=True)

    # COMPLETED (STAFF OVERRIDE)
    @discord.ui.button(label="Completed", style=discord.ButtonStyle.secondary, emoji="✅")
    async def completed(self, interaction: discord.Interaction, button: Button):

        pending_reviews[self.user_id] = True

        await interaction.response.send_message(
            "Marked complete. Review prompt sent.",
            ephemeral=True
        )

        user = await bot.fetch_user(self.user_id)

        try:
            dm = await user.send("⭐ Send a review?")
            await dm.edit(view=ReviewView(self.user_id))
        except:
            pass


# -----------------------------
# ORDER MODAL
# -----------------------------
class OrderModal(Modal, title="Place an Order"):
    item = TextInput(label="Item", required=True)
    quantity = TextInput(label="Quantity (1-23)", required=True)
    code = TextInput(label="Code", required=True)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            qty = int(self.quantity.value)
            if qty < 1 or qty > 23:
                raise ValueError()
        except:
            return await interaction.response.send_message("❌ Invalid quantity", ephemeral=True)

        channel = bot.get_channel(ORDER_CHANNEL_ID) or await bot.fetch_channel(ORDER_CHANNEL_ID)

        embed = discord.Embed(title="📦 New Order", color=discord.Color.blue())
        embed.add_field(name="Customer", value=interaction.user.mention, inline=False)
        embed.add_field(name="Item", value=self.item.value, inline=True)
        embed.add_field(name="Quantity", value=str(qty), inline=True)
        embed.add_field(name="Code", value=self.code.value, inline=False)

        view = StaffView(interaction.user.id, self.code.value)

        msg = await channel.send(embed=embed, view=view)

        active_orders[msg.id] = {
            "user_id": interaction.user.id,
            "code": self.code.value
        }

        await interaction.response.send_message("Order sent!", ephemeral=True)


# -----------------------------
# ORDER PANEL
# -----------------------------
class OrderPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Place Order", style=discord.ButtonStyle.green)
    async def order(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(OrderModal())


# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
@commands.has_permissions(administrator=True)
async def order(ctx):
    embed = discord.Embed(
        title="Place an Order",
        color=discord.Color.red()
    )

    await ctx.send(embed=embed, view=OrderPanel())


bot.run(TOKEN)
