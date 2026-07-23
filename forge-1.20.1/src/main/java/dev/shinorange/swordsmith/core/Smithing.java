package dev.shinorange.swordsmith.core;

import dev.shinorange.swordsmith.item.HeatableItem;
import dev.shinorange.swordsmith.registry.ModRegistry;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

/** The anvil forging chain: what each workpiece becomes and how many strikes it takes. */
public final class Smithing {
	public record Forging(Item output, int strikes) {
	}

	private static Map<Item, Forging> forgingSteps;

	private static Map<Item, Forging> steps() {
		if (forgingSteps == null) {
			forgingSteps = new HashMap<>();
			forgingSteps.put(ModRegistry.IRON_BLOOM.get(), new Forging(ModRegistry.STEEL_BILLET.get(), 8));
			forgingSteps.put(ModRegistry.STEEL_BILLET.get(), new Forging(ModRegistry.BLADE_PREFORM.get(), 10));
			forgingSteps.put(ModRegistry.BLADE_PREFORM.get(), new Forging(ModRegistry.ROUGH_BLADE.get(), 12));
			forgingSteps.put(ModRegistry.CRACKED_BLADE.get(), new Forging(ModRegistry.ROUGH_BLADE.get(), 6));
		}
		return forgingSteps;
	}

	public static Forging forgingOf(Item item) {
		return steps().get(item);
	}

	public static boolean isHeatable(ItemStack stack) {
		return stack.getItem() instanceof HeatableItem || stack.is(Items.RAW_IRON);
	}

	private Smithing() {
	}
}
