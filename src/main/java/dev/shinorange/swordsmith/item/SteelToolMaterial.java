package dev.shinorange.swordsmith.item;

import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.block.Block;
import net.minecraft.item.ToolMaterial;
import net.minecraft.recipe.Ingredient;
import net.minecraft.registry.tag.BlockTags;
import net.minecraft.registry.tag.TagKey;

/**
 * Hand-forged, quenched and tempered steel: better than vanilla iron in every
 * way that matters to a blade. Repairable with a spare sharpened blade.
 */
public class SteelToolMaterial implements ToolMaterial {
	public static final SteelToolMaterial INSTANCE = new SteelToolMaterial();

	@Override
	public int getDurability() {
		return 780;
	}

	@Override
	public float getMiningSpeedMultiplier() {
		return 6.5f;
	}

	@Override
	public float getAttackDamage() {
		return 3.0f;
	}

	@Override
	public TagKey<Block> getInverseTag() {
		return BlockTags.INCORRECT_FOR_IRON_TOOL;
	}

	@Override
	public int getEnchantability() {
		return 14;
	}

	@Override
	public Ingredient getRepairIngredient() {
		return Ingredient.ofItems(ModItems.SHARP_BLADE);
	}
}
