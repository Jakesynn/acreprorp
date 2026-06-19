import os
import discord
from discord.ext import commands
from discord.ui import View, Modal, TextInput
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ORDER_CHANNEL_ID = int(os.getenv("ORDER_CHANNEL_ID"))
PAYMENT_CHANNEL_ID = int(os.getenv("PAYMENT_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# -----------------------------
# ORDER MODAL
# -----------------------------
class OrderModal(Modal, title="Place an Order"):
    item = TextInput(label="What item would you like?", required=True)
    quantity = TextInput(label="Quantity (1-23)", required=True)
    code = TextInput(label="What code?", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Quantity must be a number between 1 and 23.",
                ephemeral=True
            )

        if qty < 1 or qty > 23:
            return await interaction.response.send_message(
                "❌ Quantity must be between 1 and 23.",
                ephemeral=True
            )

        channel = bot.get_channel(ORDER_CHANNEL_ID) or await bot.fetch_channel(ORDER_CHANNEL_ID)

        embed = discord.Embed(
            title="📦 New Order",
            color=discord.Color.blue()
        )

        embed.add_field(name="Customer", value=interaction.user.mention, inline=False)
        embed.add_field(name="Item", value=self.item.value, inline=True)
        embed.add_field(name="Quantity", value=str(qty), inline=True)
        embed.add_field(name="Code", value=self.code.value, inline=False)

        view = StaffView(
            user_id=interaction.user.id,
            code=self.code.value
        )

        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            "✅ Your order has been submitted!",
            ephemeral=True
        )


# -----------------------------
# ORDER PANEL BUTTON
# -----------------------------
class OrderPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Place Order",
        style=discord.ButtonStyle.green,
        custom_id="place_order"
    )
    async def place_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OrderModal())


# -----------------------------
# STAFF ORDER CONTROL PANEL
# -----------------------------
class StaffView(View):
    def __init__(self, user_id: int, code: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.code = code
        self.payment_done = False

    # ---------------- PAYMENT BUTTON ----------------
    @discord.ui.button(
        label="Needs Payment",
        style=discord.ButtonStyle.primary,
        emoji="💳"
    )
    async def payment(self, interaction: discord.Interaction, button: discord.ui.Button):

        payment_channel = bot.get_channel(PAYMENT_CHANNEL_ID) or await bot.fetch_channel(PAYMENT_CHANNEL_ID)
        customer = await bot.fetch_user(self.user_id)

        thread = await payment_channel.create_thread(
            name=f"payment-{customer.name}",
            type=discord.ChannelType.private_thread
        )

        # add staff + customer
        try:
            await thread.add_user(interaction.user)
        except:
            pass

        try:
            member = interaction.guild.get_member(self.user_id)
            if member:
                await thread.add_user(member)
        except:
            pass

        await thread.send(
            f"💳 Payment required\n"
            f"Customer: {customer.mention}\n"
            f"Staff: {interaction.user.mention}"
        )

        self.payment_done = True

        await interaction.response.send_message(
            f"✅ Payment thread created: {thread.mention}",
            ephemeral=True
        )

    # ---------------- READY BUTTON ----------------
    @discord.ui.button(
        label="Ready To Collect",
        style=discord.ButtonStyle.green,
        emoji="📦"
    )
    async def ready(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await bot.fetch_user(self.user_id)

            await user.send(
                f"🟢 Your order is ready to collect!\n\n"
                f"Join code: **{self.code}**\n\n"
                f"You have 5–10 minutes to collect it."
            )

            await interaction.response.send_message(
                "✅ Customer notified.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Could not DM user.",
                ephemeral=True
            )

    # ---------------- COMPLETED BUTTON ----------------
    @discord.ui.button(
        label="Completed",
        style=discord.ButtonStyle.secondary,
        emoji="✅"
    )
    async def completed(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed.from_dict(interaction.message.embeds[0].to_dict())
        embed.color = discord.Color.green()

        embed.add_field(
            name="Status",
            value="✅ Parcel has been delivered.",
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=None)


# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# -----------------------------
# ORDER PANEL COMMAND
# -----------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def order(ctx):
    embed = discord.Embed(
        title="Hey, come place an order!",
        description="Click the green button below to place an order.",
        color=discord.Color.red()
    )

    await ctx.send(embed=embed, view=OrderPanel())


bot.run(TOKEN)
