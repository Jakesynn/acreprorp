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


# =========================================================
# REVIEW SYSTEM
# =========================================================
class ReviewModal(Modal, title="Customer Experience Review"):
    stars = TextInput(
        label="Overall Rating (1 - 5 Stars)",
        placeholder="Enter a number from 1 to 5",
        required=True
    )

    reason = TextInput(
        label="Tell us about your experience",
        style=discord.TextStyle.paragraph,
        placeholder="What went well or what could be improved?",
        required=True
    )

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
                "❌ Please enter a valid rating between 1 and 5 stars.",
                ephemeral=True
            )

        channel = bot.get_channel(REVIEW_CHANNEL_ID) or await bot.fetch_channel(REVIEW_CHANNEL_ID)

        embed = discord.Embed(
            title="⭐ New Customer Review Received",
            color=discord.Color.gold()
        )

        embed.add_field(name="Customer", value=interaction.user.mention, inline=False)
        embed.add_field(name="Rating", value=f"{stars}/5 Stars", inline=True)
        embed.add_field(name="Feedback", value=self.reason.value, inline=False)

        embed.set_footer(text="Automated review system")

        await channel.send(embed=embed)

        pending_reviews.pop(self.user_id, None)

        await interaction.response.send_message(
            "✅ Thank you for taking the time to leave a review. We appreciate your feedback!",
            ephemeral=True
        )


class ReviewView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(
        label="Write a Review",
        style=discord.ButtonStyle.primary,
        emoji="⭐"
    )
    async def review_button(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ This review prompt is not linked to your account.",
                ephemeral=True
            )

        await interaction.response.send_modal(ReviewModal(self.user_id))


# =========================================================
# CUSTOMER COLLECTION SYSTEM
# =========================================================
class CollectView(View):
    def __init__(self, message_id: int, user_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.user_id = user_id

    @discord.ui.button(
        label="Confirm Collection",
        style=discord.ButtonStyle.success,
        emoji="📦"
    )
    async def collected(self, interaction: discord.Interaction, button: Button):

        order = active_orders.get(self.message_id)
        if not order:
            return await interaction.response.send_message(
                "❌ This order could not be found or may have expired.",
                ephemeral=True
            )

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ This confirmation link does not belong to your account.",
                ephemeral=True
            )

        pending_reviews[self.user_id] = True

        await interaction.response.send_message(
            "📩 Thank you for confirming collection.\nWould you like to leave a review for your experience?",
            view=ReviewView(self.user_id),
            ephemeral=True
        )


# =========================================================
# STAFF ORDER CONTROL PANEL
# =========================================================
class StaffView(View):
    def __init__(self, user_id: int, code: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.code = code

    # ---------------- PAYMENT ----------------
    @discord.ui.button(
        label="Mark as Payment Required",
        style=discord.ButtonStyle.primary,
        emoji="💳"
    )
    async def payment(self, interaction: discord.Interaction, button: Button):

        channel = bot.get_channel(PAYMENT_CHANNEL_ID) or await bot.fetch_channel(PAYMENT_CHANNEL_ID)
        customer = await bot.fetch_user(self.user_id)

        thread = await channel.create_thread(
            name=f"Payment Discussion - {customer.name}",
            type=discord.ChannelType.private_thread
        )

        await thread.add_user(interaction.user)

        member = interaction.guild.get_member(self.user_id)
        if member:
            await thread.add_user(member)

        await thread.send(
            f"💳 **Payment Required**\n\n"
            f"Customer: {customer.mention}\n"
            f"Handled by: {interaction.user.mention}\n\n"
            f"Please complete payment to proceed with the order."
        )

        await interaction.response.send_message(
            f"✅ Payment thread successfully created: {thread.mention}",
            ephemeral=True
        )

    # ---------------- READY ----------------
    @discord.ui.button(
        label="Mark as Ready for Collection",
        style=discord.ButtonStyle.green,
        emoji="📦"
    )
    async def ready(self, interaction: discord.Interaction, button: Button):

        user = await bot.fetch_user(self.user_id)

        dm = await user.send(
            "📦 **Your order is now ready for collection**\n\n"
            f"🔑 Collection Code: **{self.code}**\n\n"
            "Please confirm collection once you have received your order."
        )

        view = CollectView(dm.id, self.user_id)
        await dm.edit(view=view)

        await interaction.response.send_message(
            "✅ Customer has been notified and can now confirm collection.",
            ephemeral=True
        )

    # ---------------- COMPLETED ----------------
    @discord.ui.button(
        label="Mark as Completed",
        style=discord.ButtonStyle.secondary,
        emoji="✅"
    )
    async def completed(self, interaction: discord.Interaction, button: Button):

        pending_reviews[self.user_id] = True

        await interaction.response.send_message(
            "✅ Order marked as completed. Sending review request to customer.",
            ephemeral=True
        )

        try:
            user = await bot.fetch_user(self.user_id)

            dm = await user.send(
                "⭐ **We would love your feedback**\n\n"
                "Your order has been completed.\n"
                "Please leave a review about your experience."
            )

            await dm.edit(view=ReviewView(self.user_id))

        except:
            pass


# =========================================================
# ORDER CREATION SYSTEM
# =========================================================
class OrderModal(Modal, title="Place Your Order"):
    item = TextInput(label="Item Name", required=True)
    quantity = TextInput(label="Quantity (1 - 23)", required=True)
    code = TextInput(label="Order / Access Code", required=True)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            qty = int(self.quantity.value)
            if qty < 1 or qty > 23:
                raise ValueError()
        except:
            return await interaction.response.send_message(
                "❌ Please enter a valid quantity between 1 and 23.",
                ephemeral=True
            )

        channel = bot.get_channel(ORDER_CHANNEL_ID) or await bot.fetch_channel(ORDER_CHANNEL_ID)

        embed = discord.Embed(
            title="📦 New Customer Order Received",
            description="A new order has been placed and requires staff processing.",
            color=discord.Color.blue()
        )

        embed.add_field(name="Customer", value=interaction.user.mention, inline=False)
        embed.add_field(name="Item Requested", value=self.item.value, inline=True)
        embed.add_field(name="Quantity", value=str(qty), inline=True)
        embed.add_field(name="Order Code", value=self.code.value, inline=False)

        embed.set_footer(text="Order Management System")

        view = StaffView(interaction.user.id, self.code.value)

        msg = await channel.send(embed=embed, view=view)

        active_orders[msg.id] = {
            "user_id": interaction.user.id,
            "code": self.code.value
        }

        await interaction.response.send_message(
            "✅ Your order has been successfully submitted. Our team will process it shortly.",
            ephemeral=True
        )


# =========================================================
# ORDER PANEL
# =========================================================
class OrderPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Place a New Order",
        style=discord.ButtonStyle.success,
        emoji="🛒"
    )
    async def order_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(OrderModal())


# =========================================================
# BOT EVENTS
# =========================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
@commands.has_permissions(administrator=True)
async def order(ctx):

    embed = discord.Embed(
        title="🛒 Order Portal",
        description="Click the button below to begin placing your order.\nOur staff will process it as soon as possible.",
        color=discord.Color.red()
    )

    await ctx.send(embed=embed, view=OrderPanel())


bot.run(TOKEN)
