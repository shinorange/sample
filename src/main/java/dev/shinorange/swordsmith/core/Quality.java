package dev.shinorange.swordsmith.core;

import dev.shinorange.swordsmith.registry.ModComponents;
import net.minecraft.component.type.AttributeModifierSlot;
import net.minecraft.component.type.AttributeModifiersComponent;
import net.minecraft.entity.attribute.EntityAttributeModifier;
import net.minecraft.entity.attribute.EntityAttributes;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.text.MutableText;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
import net.minecraft.util.math.MathHelper;

/**
 * Craftsmanship rules. A strike lands "perfect" in the bright orange-yellow
 * band (900-1150 C) where real steel moves best; the ideal quench is dead
 * center of the hardening window (~865 C). The finished sword's attack damage
 * scales with the result: a sloppy sword is barely better than vanilla iron,
 * a masterwork clearly outclasses it.
 */
public final class Quality {
	public static final float PERFECT_STRIKE_MIN = 900f;
	public static final float PERFECT_STRIKE_MAX = 1150f;
	public static final float QUENCH_IDEAL = 865f;

	/** Score of a single anvil strike at the given metal temperature. */
	public static float strikeScore(float temp) {
		return temp >= PERFECT_STRIKE_MIN && temp <= PERFECT_STRIKE_MAX ? 1.0f : 0.6f;
	}

	/** Score of a quench at the given temperature (already inside the window). */
	public static float quenchScore(float temp) {
		return MathHelper.clamp(1f - Math.abs(temp - QUENCH_IDEAL) / 100f, 0.4f, 1.0f);
	}

	/** Copies the quality history from one workpiece stage to the next. */
	public static void carry(ItemStack from, ItemStack to) {
		QualityData data = from.get(ModComponents.QUALITY);
		if (data != null) {
			to.set(ModComponents.QUALITY, data);
		}
	}

	/** Attack modifiers for a finished sword: 6.6-8.5 total damage by quality. */
	public static AttributeModifiersComponent swordAttributes(float quality) {
		double damage = 3.5 + 4.0 * quality;
		return AttributeModifiersComponent.builder()
				.add(EntityAttributes.GENERIC_ATTACK_DAMAGE,
						new EntityAttributeModifier(Item.BASE_ATTACK_DAMAGE_MODIFIER_ID, damage,
								EntityAttributeModifier.Operation.ADD_VALUE),
						AttributeModifierSlot.MAINHAND)
				.add(EntityAttributes.GENERIC_ATTACK_SPEED,
						new EntityAttributeModifier(Item.BASE_ATTACK_SPEED_MODIFIER_ID, -2.2,
								EntityAttributeModifier.Operation.ADD_VALUE),
						AttributeModifierSlot.MAINHAND)
				.build();
	}

	/** Colored grade name for a final quality value. */
	public static MutableText gradeText(float quality) {
		if (quality < 0.60f) {
			return Text.translatable("quality.swordsmith.plain").formatted(Formatting.GRAY);
		}
		if (quality < 0.72f) {
			return Text.translatable("quality.swordsmith.fine").formatted(Formatting.GREEN);
		}
		if (quality < 0.84f) {
			return Text.translatable("quality.swordsmith.superior").formatted(Formatting.AQUA);
		}
		if (quality < 0.95f) {
			return Text.translatable("quality.swordsmith.master").formatted(Formatting.LIGHT_PURPLE);
		}
		return Text.translatable("quality.swordsmith.legend").formatted(Formatting.GOLD);
	}

	private Quality() {
	}
}
