package dev.shinorange.swordsmith.client.screen;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.menu.ForgeMenu;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.ChatFormatting;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.item.Items;

/**
 * Vanilla-styled forge screen: zone-marked thermometer with a workpiece
 * marker, furnace-style fuel flame, bellows blast bar and a progress arrow.
 * Every gauge explains itself in a hover tooltip.
 */
public class ForgeScreen extends AbstractContainerScreen<ForgeMenu> {
	private static final ResourceLocation TEXTURE = Swordsmith.id("textures/gui/forge.png");

	public ForgeScreen(ForgeMenu menu, Inventory playerInventory, Component title) {
		super(menu, playerInventory, title);
		this.imageWidth = 176;
		this.imageHeight = 166;
		this.inventoryLabelY = this.imageHeight - 94;
	}

	@Override
	protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
		int left = this.leftPos;
		int top = this.topPos;
		graphics.blit(TEXTURE, left, top, 0, 0, this.imageWidth, this.imageHeight);

		int fireTemp = this.menu.getFireTemp();
		int fireHeight = gaugeHeight(fireTemp);
		if (fireHeight > 0) {
			graphics.fill(left + 149, top + 70 - fireHeight, left + 157, top + 70,
					0xFF000000 | Heat.barColor(fireTemp));
		}
		if (!this.menu.getWorkpiece().isEmpty()) {
			int markerHeight = gaugeHeight(this.menu.getWorkTemp());
			graphics.fill(left + 147, top + 69 - markerHeight, left + 159, top + 70 - markerHeight, 0xFFF5F5F5);
		}

		int fuel = this.menu.getFuelSeconds();
		if (fuel > 0) {
			int flame = Math.max(1, Math.round(13f * Math.min(1f, fuel / 300f)));
			graphics.blit(TEXTURE, left + 28, top + 35 + 13 - flame, 176, 13 - flame, 13, flame);
		}

		int air = this.menu.getAirflowPercent();
		if (air > 0) {
			graphics.blit(TEXTURE, left + 49, top + 58, 176, 16, Math.max(1, 24 * air / 100), 5);
		}

		int progress = this.menu.getProgressPercent();
		if (progress > 0) {
			graphics.blit(TEXTURE, left + 103, top + 36, 176, 24, Math.max(1, 22 * progress / 100), 13);
		}
	}

	@Override
	protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
		super.renderLabels(graphics, mouseX, mouseY);
		Component label = Component.literal(this.menu.getFireTemp() + "°C");
		int width = this.font.width(label);
		graphics.drawString(this.font, label, 153 - width / 2, 74, 0x404040, false);
	}

	@Override
	public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
		this.renderBackground(graphics);
		super.render(graphics, mouseX, mouseY, partialTick);
		this.renderTooltip(graphics, mouseX, mouseY);

		if (this.isHovering(146, 13, 16, 59, mouseX, mouseY)) {
			List<Component> lines = new ArrayList<>();
			int fireTemp = this.menu.getFireTemp();
			lines.add(Component.translatable("gui.swordsmith.fire", fireTemp, Heat.label(fireTemp)));
			if (!this.menu.getWorkpiece().isEmpty()) {
				int workTemp = this.menu.getWorkTemp();
				lines.add(Component.translatable("gui.swordsmith.workpiece_temp", workTemp, Heat.label(workTemp)));
			}
			lines.add(Component.translatable("gui.swordsmith.zone.temper").withStyle(ChatFormatting.AQUA));
			lines.add(Component.translatable("gui.swordsmith.zone.forging").withStyle(ChatFormatting.GOLD));
			lines.add(Component.translatable("gui.swordsmith.zone.quench").withStyle(ChatFormatting.RED));
			lines.add(Component.translatable("gui.swordsmith.zone.smelt").withStyle(ChatFormatting.YELLOW));
			graphics.renderComponentTooltip(this.font, lines, mouseX, mouseY);
		} else if (this.isHovering(27, 34, 15, 15, mouseX, mouseY)) {
			graphics.renderTooltip(this.font,
					Component.translatable("gui.swordsmith.fuel", this.menu.getFuelSeconds()), mouseX, mouseY);
		} else if (this.isHovering(48, 56, 26, 8, mouseX, mouseY)) {
			List<Component> lines = new ArrayList<>();
			lines.add(Component.translatable("gui.swordsmith.airflow", this.menu.getAirflowPercent()));
			lines.add(Component.translatable("gui.swordsmith.airflow_hint").withStyle(ChatFormatting.GRAY));
			graphics.renderComponentTooltip(this.font, lines, mouseX, mouseY);
		} else if (this.menu.getProgressPercent() > 0 && this.isHovering(102, 35, 24, 15, mouseX, mouseY)) {
			String key = this.menu.getWorkpiece().is(Items.RAW_IRON)
					? "gui.swordsmith.progress.smelt" : "gui.swordsmith.progress.temper";
			graphics.renderTooltip(this.font,
					Component.translatable(key, this.menu.getProgressPercent()), mouseX, mouseY);
		}
	}

	private static int gaugeHeight(int temp) {
		return Math.round(54f * Mth.clamp((temp - 20f) / 1280f, 0f, 1f));
	}
}
