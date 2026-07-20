package dev.shinorange.swordsmith.registry;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.item.ForgedSwordItem;
import dev.shinorange.swordsmith.item.HeatableItem;
import dev.shinorange.swordsmith.item.HintedBlockItem;
import dev.shinorange.swordsmith.item.HintedItem;
import dev.shinorange.swordsmith.item.SteelToolMaterial;
import net.minecraft.item.Item;
import net.minecraft.item.SwordItem;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;

public final class ModItems {
	// --- workpieces, in process order -----------------------------------------
	public static final Item IRON_BLOOM = workpiece("iron_bloom");
	public static final Item STEEL_BILLET = workpiece("steel_billet");
	public static final Item BLADE_PREFORM = workpiece("blade_preform");
	public static final Item ROUGH_BLADE = workpiece("rough_blade");
	public static final Item CRACKED_BLADE = workpiece("cracked_blade");
	public static final Item QUENCHED_BLADE = workpiece("quenched_blade");
	public static final Item TEMPERED_BLADE = workpiece("tempered_blade");
	public static final Item SHARP_BLADE = workpiece("sharp_blade");

	// --- hilt furniture -------------------------------------------------------
	public static final Item SWORD_GUARD = register("sword_guard",
			new HintedItem(hint("sword_guard"), new Item.Settings().maxCount(16)));
	public static final Item SWORD_GRIP = register("sword_grip",
			new HintedItem(hint("sword_grip"), new Item.Settings().maxCount(16)));
	public static final Item SWORD_POMMEL = register("sword_pommel",
			new HintedItem(hint("sword_pommel"), new Item.Settings().maxCount(16)));

	// --- the smith's tools ----------------------------------------------------
	public static final Item SMITHING_HAMMER = register("smithing_hammer",
			new HintedItem(hint("smithing_hammer"), new Item.Settings().maxDamage(512)));
	public static final Item SMITHING_TONGS = register("smithing_tongs",
			new HintedItem(hint("smithing_tongs"), new Item.Settings().maxDamage(256)));
	public static final Item BELLOWS = register("bellows",
			new HintedItem(hint("bellows"), new Item.Settings().maxDamage(256)));

	// --- the reward -----------------------------------------------------------
	public static final Item FORGED_STEEL_SWORD = register("forged_steel_sword",
			new ForgedSwordItem(new Item.Settings()
					.maxCount(1)
					.attributeModifiers(SwordItem.createAttributeModifiers(SteelToolMaterial.INSTANCE, 3, -2.2f))));

	// --- block items ----------------------------------------------------------
	public static final Item FORGE = register("forge",
			new HintedBlockItem(ModBlocks.FORGE, "block.swordsmith.forge.hint", new Item.Settings()));
	public static final Item SMITHING_ANVIL = register("smithing_anvil",
			new HintedBlockItem(ModBlocks.SMITHING_ANVIL, "block.swordsmith.smithing_anvil.hint", new Item.Settings()));
	public static final Item QUENCHING_BARREL = register("quenching_barrel",
			new HintedBlockItem(ModBlocks.QUENCHING_BARREL, "block.swordsmith.quenching_barrel.hint", new Item.Settings()));
	public static final Item WHETSTONE = register("whetstone",
			new HintedBlockItem(ModBlocks.WHETSTONE, "block.swordsmith.whetstone.hint", new Item.Settings()));

	private static Item workpiece(String name) {
		// One at a time, like a real smith — and metal does not burn in fire.
		return register(name, new HeatableItem(hint(name), new Item.Settings().maxCount(1).fireproof()));
	}

	private static String hint(String name) {
		return "item.swordsmith." + name + ".hint";
	}

	private static Item register(String name, Item item) {
		return Registry.register(Registries.ITEM, Swordsmith.id(name), item);
	}

	public static void init() {
	}

	private ModItems() {
	}
}
