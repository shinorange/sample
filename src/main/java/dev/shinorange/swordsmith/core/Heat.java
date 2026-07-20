package dev.shinorange.swordsmith.core;

import dev.shinorange.swordsmith.registry.ModComponents;
import net.minecraft.item.ItemStack;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
import net.minecraft.util.math.MathHelper;
import net.minecraft.world.World;

/**
 * All the metallurgy numbers in one place. Temperatures are in degrees Celsius
 * and roughly follow real smithing practice:
 *
 * - a charcoal forge idles around 900 C; hard bellows work pushes it near 1280 C
 * - iron ore reduces to a spongy bloom above ~1150 C (bloomery smelting)
 * - steel is forged between ~720 C (dull red) and white heat
 * - hardening quench happens from the 780-950 C "cherry red" range;
 *   hotter and the blade cracks, cooler and no martensite forms
 * - tempering is a gentle 150-400 C soak; overshooting anneals the blade
 */
public final class Heat {
	public static final float AMBIENT = 20f;
	public static final float FORGE_BASE_TEMP = 900f;
	public static final float BELLOWS_BONUS = 380f;

	public static final float FORGING_MIN = 720f;
	public static final float QUENCH_MIN = 780f;
	public static final float QUENCH_MAX = 950f;
	public static final float TEMPER_MIN = 150f;
	public static final float TEMPER_MAX = 400f;
	public static final float ANNEAL_TEMP = 460f;
	public static final float SMELT_TEMP = 1150f;
	public static final float BURN_TEMP = 150f;
	public static final float COLD_WORK_MAX = 60f;
	public static final float STRIKE_COOLING = 12f;
	public static final float MAX_TEMP = 1300f;

	/** Newton cooling time constant, in ticks (~80 s to lose 63% of the excess heat). */
	public static final double COOL_TAU_TICKS = 1600.0;

	public static final int SMELT_TICKS = 600;
	public static final int TEMPER_TICKS = 400;
	public static final int GRIND_USES = 24;
	public static final int PEEN_STRIKES = 3;

	/** Current temperature of a stack, applying lazy exponential cooling. */
	public static float current(World world, ItemStack stack) {
		HeatData data = stack.get(ModComponents.HEAT);
		if (data == null) {
			return AMBIENT;
		}
		long elapsed = Math.max(0L, world.getTime() - data.time());
		return (float) (AMBIENT + (data.temperature() - AMBIENT) * Math.exp(-elapsed / COOL_TAU_TICKS));
	}

	/** Stamps a temperature onto a stack; near-ambient clears the component. */
	public static void set(World world, ItemStack stack, float temperature) {
		if (temperature <= AMBIENT + 5f) {
			stack.remove(ModComponents.HEAT);
		} else {
			stack.set(ModComponents.HEAT, new HeatData(Math.min(temperature, MAX_TEMP), world.getTime()));
		}
	}

	/** Human-readable glow color for a temperature, like real steel. */
	public static MutableText label(float t) {
		if (t < COLD_WORK_MAX) {
			return Text.translatable("heat.swordsmith.cold").formatted(Formatting.GRAY);
		}
		if (t < 500f) {
			return Text.translatable("heat.swordsmith.black").formatted(Formatting.DARK_GRAY);
		}
		if (t < FORGING_MIN) {
			return Text.translatable("heat.swordsmith.dark_red").formatted(Formatting.DARK_RED);
		}
		if (t < 900f) {
			return Text.translatable("heat.swordsmith.red").formatted(Formatting.RED);
		}
		if (t < 1050f) {
			return Text.translatable("heat.swordsmith.orange").formatted(Formatting.GOLD);
		}
		if (t < 1200f) {
			return Text.translatable("heat.swordsmith.yellow").formatted(Formatting.YELLOW);
		}
		return Text.translatable("heat.swordsmith.white").formatted(Formatting.WHITE);
	}

	/** 0..13 gauge for the item duration bar. */
	public static int barStep(float t) {
		return Math.round(MathHelper.clamp((t - AMBIENT) / (MAX_TEMP - AMBIENT), 0f, 1f) * 13f);
	}

	/** Black-body-ish bar color: dark red -> orange -> near white. */
	public static int barColor(float t) {
		float f = MathHelper.clamp((t - AMBIENT) / (MAX_TEMP - AMBIENT), 0f, 1f);
		int r;
		int g;
		int b;
		if (f < 0.5f) {
			float k = f / 0.5f;
			r = (int) MathHelper.lerp(k, 90f, 255f);
			g = (int) MathHelper.lerp(k, 25f, 90f);
			b = 20;
		} else {
			float k = (f - 0.5f) / 0.5f;
			r = 255;
			g = (int) MathHelper.lerp(k, 90f, 230f);
			b = (int) MathHelper.lerp(k, 20f, 160f);
		}
		return (r << 16) | (g << 8) | b;
	}

	private Heat() {
	}
}
