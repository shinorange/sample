package dev.shinorange.swordsmith.client;

import dev.shinorange.swordsmith.core.Heat;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.util.Mth;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.client.gui.overlay.ForgeGui;

/**
 * A compact live temperature readout above the right end of the hotbar
 * whenever a heated workpiece is in either hand, with tick marks at 720 C
 * (forging) and the 780-950 C quench window.
 */
public final class HeatHud {
	public static void render(ForgeGui gui, GuiGraphics graphics, float partialTick, int width, int height) {
		Minecraft minecraft = Minecraft.getInstance();
		LocalPlayer player = minecraft.player;
		if (player == null || minecraft.options.hideGui) {
			return;
		}
		ItemStack stack = player.getMainHandItem();
		if (!Heat.hasHeat(stack)) {
			stack = player.getOffhandItem();
			if (!Heat.hasHeat(stack)) {
				return;
			}
		}
		float temp = Heat.current(player.level(), stack);
		if (temp <= Heat.AMBIENT + 5f) {
			return;
		}

		int x = width / 2 + 94;
		int y = height - 42;
		int color = 0xFF000000 | Heat.barColor(temp);

		graphics.fill(x - 3, y - 3, x + 47, y + 15, 0x90101014);
		graphics.drawString(minecraft.font, Component.literal((int) temp + "°C"), x, y, color, true);

		int barWidth = 44;
		int gaugeY = y + 10;
		int filled = (int) (barWidth * Mth.clamp((temp - Heat.AMBIENT) / (Heat.MAX_TEMP - Heat.AMBIENT), 0f, 1f));
		graphics.fill(x, gaugeY, x + barWidth, gaugeY + 3, 0xFF2A2A2E);
		if (filled > 0) {
			graphics.fill(x, gaugeY, x + filled, gaugeY + 3, color);
		}
		for (float tick : new float[]{Heat.FORGING_MIN, Heat.QUENCH_MIN, Heat.QUENCH_MAX}) {
			int tickX = x + (int) (barWidth * (tick - Heat.AMBIENT) / (Heat.MAX_TEMP - Heat.AMBIENT));
			graphics.fill(tickX, gaugeY - 1, tickX + 1, gaugeY + 4, 0xFFE8E8E8);
		}
	}

	private HeatHud() {
	}
}
