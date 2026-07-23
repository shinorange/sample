package dev.shinorange.swordsmith.core;

import java.util.UUID;
import net.minecraft.ChatFormatting;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.ai.attributes.AttributeModifier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.item.ItemStack;

/**
 * Craftsmanship rules, NBT edition. Strikes in the 900-1150 C band land
 * perfect; the ideal quench is 865 C. The history rides on the workpiece tag
 * through every stage and collapses into per-stack attribute modifiers
 * (attack damage 6.6-8.5 total) at hilt assembly.
 */
public final class Quality {
	public static final String QUALITY_TAG = "SwordsmithQuality";
	public static final String SWORD_QUALITY_KEY = "SwordsmithSwordQuality";
	public static final String GRIND_KEY = "SwordsmithGrind";

	public static final float PERFECT_STRIKE_MIN = 900f;
	public static final float PERFECT_STRIKE_MAX = 1150f;
	public static final float QUENCH_IDEAL = 865f;

	private static final UUID BASE_ATTACK_DAMAGE_UUID = UUID.fromString("CB3F55D3-645C-4F38-A497-9C13A33DB5CF");
	private static final UUID BASE_ATTACK_SPEED_UUID = UUID.fromString("FA233E1C-4180-4865-B01B-BCCE9785ACA3");

	public static float strikeScore(float temp) {
		return temp >= PERFECT_STRIKE_MIN && temp <= PERFECT_STRIKE_MAX ? 1.0f : 0.6f;
	}

	public static float quenchScore(float temp) {
		return Mth.clamp(1f - Math.abs(temp - QUENCH_IDEAL) / 100f, 0.4f, 1.0f);
	}

	public static void addStrike(ItemStack stack, float score) {
		CompoundTag tag = stack.getOrCreateTagElement(QUALITY_TAG);
		tag.putFloat("Sum", tag.getFloat("Sum") + score);
		tag.putInt("Count", tag.getInt("Count") + 1);
	}

	public static void setQuench(ItemStack stack, float score) {
		stack.getOrCreateTagElement(QUALITY_TAG).putFloat("Quench", score);
	}

	/** Copies the quality history from one workpiece stage to the next. */
	public static void carry(ItemStack from, ItemStack to) {
		CompoundTag tag = from.getTagElement(QUALITY_TAG);
		if (tag != null) {
			to.getOrCreateTag().put(QUALITY_TAG, tag.copy());
		}
	}

	public static int strikeCount(ItemStack stack) {
		CompoundTag tag = stack.getTagElement(QUALITY_TAG);
		return tag == null ? 0 : tag.getInt("Count");
	}

	public static float strikeAverage(ItemStack stack) {
		CompoundTag tag = stack.getTagElement(QUALITY_TAG);
		if (tag == null || tag.getInt("Count") == 0) {
			return 0.75f;
		}
		return tag.getFloat("Sum") / tag.getInt("Count");
	}

	public static float quenchValue(ItemStack stack) {
		CompoundTag tag = stack.getTagElement(QUALITY_TAG);
		return tag == null ? 0f : tag.getFloat("Quench");
	}

	/** 65% hammer work, 35% quench accuracy. */
	public static float finalQuality(ItemStack stack) {
		if (stack.getTagElement(QUALITY_TAG) == null) {
			return 0.7f;
		}
		float quench = quenchValue(stack) <= 0f ? 0.6f : quenchValue(stack);
		return Mth.clamp(0.65f * strikeAverage(stack) + 0.35f * quench, 0f, 1f);
	}

	/** Bakes the final quality into the sword: tooltip value + attributes. */
	public static void applyToSword(ItemStack sword, float quality) {
		sword.getOrCreateTag().putFloat(SWORD_QUALITY_KEY, quality);
		double damage = 3.5 + 4.0 * quality;
		sword.addAttributeModifier(Attributes.ATTACK_DAMAGE,
				new AttributeModifier(BASE_ATTACK_DAMAGE_UUID, "Weapon modifier", damage,
						AttributeModifier.Operation.ADDITION), EquipmentSlot.MAINHAND);
		sword.addAttributeModifier(Attributes.ATTACK_SPEED,
				new AttributeModifier(BASE_ATTACK_SPEED_UUID, "Weapon modifier", -2.2,
						AttributeModifier.Operation.ADDITION), EquipmentSlot.MAINHAND);
	}

	public static MutableComponent gradeText(float quality) {
		if (quality < 0.60f) {
			return Component.translatable("quality.swordsmith.plain").withStyle(ChatFormatting.GRAY);
		}
		if (quality < 0.72f) {
			return Component.translatable("quality.swordsmith.fine").withStyle(ChatFormatting.GREEN);
		}
		if (quality < 0.84f) {
			return Component.translatable("quality.swordsmith.superior").withStyle(ChatFormatting.AQUA);
		}
		if (quality < 0.95f) {
			return Component.translatable("quality.swordsmith.master").withStyle(ChatFormatting.LIGHT_PURPLE);
		}
		return Component.translatable("quality.swordsmith.legend").withStyle(ChatFormatting.GOLD);
	}

	private Quality() {
	}
}
