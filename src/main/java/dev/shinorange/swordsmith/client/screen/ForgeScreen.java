package dev.shinorange.swordsmith.client.screen;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.screen.ForgeScreenHandler;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.ingame.HandledScreen;
import net.minecraft.entity.player.PlayerInventory;
import net.minecraft.item.Items;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.MathHelper;

/**
 * Vanilla-styled forge screen: a zone-marked thermometer for the fire (with a
 * white marker for the workpiece), a furnace-like fuel flame, a bellows blast
 * bar, and a progress arrow while smelting or tempering. Every gauge explains
 * itself in a hover tooltip.
 */
public class ForgeScreen extends HandledScreen<ForgeScreenHandler> {
	private static final Identifier TEXTURE = Swordsmith.id("textures/gui/forge.png");

	public ForgeScreen(ForgeScreenHandler handler, PlayerInventory inventory, Text title) {
		super(handler, inventory, title);
		this.backgroundWidth = 176;
		this.backgroundHeight = 166;
		this.playerInventoryTitleY = this.backgroundHeight - 94;
	}

	@Override
	protected void drawBackground(DrawContext context, float delta, int mouseX, int mouseY) {
		int left = this.x;
		int top = this.y;
		context.drawTexture(TEXTURE, left, top, 0, 0, this.backgroundWidth, this.backgroundHeight);

		// Thermometer: fire temperature column plus a marker for the workpiece.
		int fireTemp = this.handler.getFireTemp();
		int fireHeight = gaugeHeight(fireTemp);
		if (fireHeight > 0) {
			context.fill(left + 149, top + 70 - fireHeight, left + 157, top + 70,
					0xFF000000 | Heat.barColor(fireTemp));
		}
		if (!this.handler.getWorkpiece().isEmpty()) {
			int markerHeight = gaugeHeight(this.handler.getWorkTemp());
			context.fill(left + 147, top + 69 - markerHeight, left + 159, top + 70 - markerHeight, 0xFFF5F5F5);
		}

		// Fuel flame, furnace-style.
		int fuel = this.handler.getFuelSeconds();
		if (fuel > 0) {
			int flame = Math.max(1, Math.round(13f * Math.min(1f, fuel / 300f)));
			context.drawTexture(TEXTURE, left + 28, top + 35 + 13 - flame, 176, 13 - flame, 13, flame);
		}

		// Bellows blast.
		int air = this.handler.getAirflowPercent();
		if (air > 0) {
			context.drawTexture(TEXTURE, left + 49, top + 58, 176, 16, Math.max(1, 24 * air / 100), 5);
		}

		// Smelting / tempering progress arrow.
		int progress = this.handler.getProgressPercent();
		if (progress > 0) {
			context.drawTexture(TEXTURE, left + 103, top + 36, 176, 24, Math.max(1, 22 * progress / 100), 13);
		}
	}

	@Override
	public void render(DrawContext context, int mouseX, int mouseY, float delta) {
		super.render(context, mouseX, mouseY, delta);
		this.drawMouseoverTooltip(context, mouseX, mouseY);

		if (this.isPointWithinBounds(146, 13, 16, 59, mouseX, mouseY)) {
			List<Text> lines = new ArrayList<>();
			int fireTemp = this.handler.getFireTemp();
			lines.add(Text.translatable("gui.swordsmith.fire", fireTemp, Heat.label(fireTemp)));
			if (!this.handler.getWorkpiece().isEmpty()) {
				int workTemp = this.handler.getWorkTemp();
				lines.add(Text.translatable("gui.swordsmith.workpiece_temp", workTemp, Heat.label(workTemp)));
			}
			lines.add(Text.translatable("gui.swordsmith.zone.temper").formatted(Formatting.AQUA));
			lines.add(Text.translatable("gui.swordsmith.zone.forging").formatted(Formatting.GOLD));
			lines.add(Text.translatable("gui.swordsmith.zone.quench").formatted(Formatting.RED));
			lines.add(Text.translatable("gui.swordsmith.zone.smelt").formatted(Formatting.YELLOW));
			context.drawTooltip(this.textRenderer, lines, mouseX, mouseY);
		} else if (this.isPointWithinBounds(27, 34, 15, 15, mouseX, mouseY)) {
			context.drawTooltip(this.textRenderer,
					Text.translatable("gui.swordsmith.fuel", this.handler.getFuelSeconds()), mouseX, mouseY);
		} else if (this.isPointWithinBounds(48, 56, 26, 8, mouseX, mouseY)) {
			List<Text> lines = new ArrayList<>();
			lines.add(Text.translatable("gui.swordsmith.airflow", this.handler.getAirflowPercent()));
			lines.add(Text.translatable("gui.swordsmith.airflow_hint").formatted(Formatting.GRAY));
			context.drawTooltip(this.textRenderer, lines, mouseX, mouseY);
		} else if (this.handler.getProgressPercent() > 0
				&& this.isPointWithinBounds(102, 35, 24, 15, mouseX, mouseY)) {
			String key = this.handler.getWorkpiece().isOf(Items.RAW_IRON)
					? "gui.swordsmith.progress.smelt" : "gui.swordsmith.progress.temper";
			context.drawTooltip(this.textRenderer,
					Text.translatable(key, this.handler.getProgressPercent()), mouseX, mouseY);
		}
	}

	private static int gaugeHeight(int temp) {
		return Math.round(54f * MathHelper.clamp((temp - 20f) / 1280f, 0f, 1f));
	}
}
