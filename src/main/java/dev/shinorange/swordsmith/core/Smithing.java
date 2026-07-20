package dev.shinorange.swordsmith.core;

import dev.shinorange.swordsmith.item.HeatableItem;
import dev.shinorange.swordsmith.registry.ModItems;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;

/** The anvil forging chain: what each workpiece becomes and how many strikes it takes. */
public final class Smithing {
	public record Forging(Item output, int strikes) {
	}

	private static Map<Item, Forging> forgingSteps;

	private static Map<Item, Forging> steps() {
		if (forgingSteps == null) {
			forgingSteps = new HashMap<>();
			// Consolidate the spongy bloom, squeezing out slag.
			forgingSteps.put(ModItems.IRON_BLOOM, new Forging(ModItems.STEEL_BILLET, 8));
			// Draw the billet out into a bar.
			forgingSteps.put(ModItems.STEEL_BILLET, new Forging(ModItems.BLADE_PREFORM, 10));
			// Set the bevels, point and tang.
			forgingSteps.put(ModItems.BLADE_PREFORM, new Forging(ModItems.ROUGH_BLADE, 12));
			// A cracked blade can be forged back into shape and re-quenched.
			forgingSteps.put(ModItems.CRACKED_BLADE, new Forging(ModItems.ROUGH_BLADE, 6));
		}
		return forgingSteps;
	}

	/** Forging step for this item on the anvil, or null if it cannot be hammered. */
	public static Forging forgingOf(Item item) {
		return steps().get(item);
	}

	/** Anything that may be placed in the forge or on the anvil to be heated. */
	public static boolean isHeatable(ItemStack stack) {
		return stack.getItem() instanceof HeatableItem || stack.isOf(Items.RAW_IRON);
	}

	private Smithing() {
	}
}
