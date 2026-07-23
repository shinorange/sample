package dev.shinorange.swordsmith.client;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.registry.ModComponents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.client.render.RenderTickCounter;
import net.minecraft.item.ItemStack;
import net.minecraft.text.Text;
import net.minecraft.util.math.MathHelper;

/**
 * A compact live temperature readout above the right end of the hotbar
 * whenever a heated workpiece is in either hand. The gauge carries tick marks
 * at 720 C (forging) and 780/950 C (the quench window), and since heat decays
 * lazily from a timestamped component, it animates smoothly with zero sync.
 */
public final class HeatHud {
	public static void render(DrawContext context, RenderTickCounter tickCounter) {
		MinecraftClient client = MinecraftClient.getInstance();
		ClientPlayerEntity player = client.player;
		if (player == null || client.options.hudHidden) {
			return;
		}
		ItemStack stack = player.getMainHandStack();
		if (stack.get(ModComponents.HEAT) == null) {
			stack = player.getOffHandStack();
			if (stack.get(ModComponents.HEAT) == null) {
				return;
			}
		}
		float temp = Heat.current(player.getWorld(), stack);
		if (temp <= Heat.AMBIENT + 5f) {
			return;
		}

		int x = context.getScaledWindowWidth() / 2 + 94;
		int y = context.getScaledWindowHeight() - 42;
		int color = 0xFF000000 | Heat.barColor(temp);

		context.fill(x - 3, y - 3, x + 47, y + 15, 0x90101014);
		context.drawText(client.textRenderer, Text.literal((int) temp + "°C"), x, y, color, true);

		int width = 44;
		int gaugeY = y + 10;
		int filled = (int) (width * MathHelper.clamp((temp - Heat.AMBIENT) / (Heat.MAX_TEMP - Heat.AMBIENT), 0f, 1f));
		context.fill(x, gaugeY, x + width, gaugeY + 3, 0xFF2A2A2E);
		if (filled > 0) {
			context.fill(x, gaugeY, x + filled, gaugeY + 3, color);
		}
		for (float tick : new float[]{Heat.FORGING_MIN, Heat.QUENCH_MIN, Heat.QUENCH_MAX}) {
			int tickX = x + (int) (width * (tick - Heat.AMBIENT) / (Heat.MAX_TEMP - Heat.AMBIENT));
			context.fill(tickX, gaugeY - 1, tickX + 1, gaugeY + 4, 0xFFE8E8E8);
		}
	}

	private HeatHud() {
	}
}
