package dev.shinorange.swordsmith.core;

import net.minecraft.ChatFormatting;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.util.Mth;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;

/**
 * The metallurgy numbers, identical to the Fabric build. 1.20.1 has no data
 * components, so the heat snapshot (temperature + game time) lives in item
 * NBT and decays lazily via Newton's law of cooling whenever it is read.
 */
public final class Heat {
	public static final String HEAT_TAG = "SwordsmithHeat";

	public static final float AMBIENT = 20f;
	public static final float FORGE_BASE_TEMP = 300f;
	public static final float BELLOWS_BONUS = 980f;

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

	public static final double COOL_TAU_TICKS = 1600.0;

	public static final int SMELT_TICKS = 600;
	public static final int TEMPER_TICKS = 400;
	public static final int GRIND_USES = 24;
	public static final int PEEN_STRIKES = 3;

	/** Stored (undecayed) temperature, for display; refreshed once a second. */
	public static float raw(ItemStack stack) {
		CompoundTag tag = stack.getTagElement(HEAT_TAG);
		return tag == null ? AMBIENT : tag.getFloat("Temp");
	}

	public static boolean hasHeat(ItemStack stack) {
		return stack.getTagElement(HEAT_TAG) != null;
	}

	/** Current temperature with lazy exponential cooling applied. */
	public static float current(Level level, ItemStack stack) {
		CompoundTag tag = stack.getTagElement(HEAT_TAG);
		if (tag == null) {
			return AMBIENT;
		}
		long elapsed = Math.max(0L, level.getGameTime() - tag.getLong("Time"));
		return (float) (AMBIENT + (tag.getFloat("Temp") - AMBIENT) * Math.exp(-elapsed / COOL_TAU_TICKS));
	}

	/** Stamps a temperature; near-ambient clears the tag. */
	public static void set(Level level, ItemStack stack, float temperature) {
		if (temperature <= AMBIENT + 5f) {
			stack.removeTagKey(HEAT_TAG);
			return;
		}
		CompoundTag tag = stack.getOrCreateTagElement(HEAT_TAG);
		tag.putFloat("Temp", Math.min(temperature, MAX_TEMP));
		tag.putLong("Time", level.getGameTime());
	}

	public static MutableComponent label(float t) {
		if (t < COLD_WORK_MAX) {
			return Component.translatable("heat.swordsmith.cold").withStyle(ChatFormatting.GRAY);
		}
		if (t < 500f) {
			return Component.translatable("heat.swordsmith.black").withStyle(ChatFormatting.DARK_GRAY);
		}
		if (t < FORGING_MIN) {
			return Component.translatable("heat.swordsmith.dark_red").withStyle(ChatFormatting.DARK_RED);
		}
		if (t < 900f) {
			return Component.translatable("heat.swordsmith.red").withStyle(ChatFormatting.RED);
		}
		if (t < 1050f) {
			return Component.translatable("heat.swordsmith.orange").withStyle(ChatFormatting.GOLD);
		}
		if (t < 1200f) {
			return Component.translatable("heat.swordsmith.yellow").withStyle(ChatFormatting.YELLOW);
		}
		return Component.translatable("heat.swordsmith.white").withStyle(ChatFormatting.WHITE);
	}

	public static int barWidth(float t) {
		return Math.round(Mth.clamp((t - AMBIENT) / (MAX_TEMP - AMBIENT), 0f, 1f) * 13f);
	}

	public static int barColor(float t) {
		float f = Mth.clamp((t - AMBIENT) / (MAX_TEMP - AMBIENT), 0f, 1f);
		int r;
		int g;
		int b;
		if (f < 0.5f) {
			float k = f / 0.5f;
			r = (int) Mth.lerp(k, 90f, 255f);
			g = (int) Mth.lerp(k, 25f, 90f);
			b = 20;
		} else {
			float k = (f - 0.5f) / 0.5f;
			r = 255;
			g = (int) Mth.lerp(k, 90f, 230f);
			b = (int) Mth.lerp(k, 20f, 160f);
		}
		return (r << 16) | (g << 8) | b;
	}

	private Heat() {
	}
}
