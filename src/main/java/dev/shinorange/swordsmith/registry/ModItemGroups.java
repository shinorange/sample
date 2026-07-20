package dev.shinorange.swordsmith.registry;

import dev.shinorange.swordsmith.Swordsmith;
import net.fabricmc.fabric.api.itemgroup.v1.FabricItemGroup;
import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;
import net.minecraft.item.ItemGroup;
import net.minecraft.item.ItemStack;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.registry.RegistryKey;
import net.minecraft.registry.RegistryKeys;
import net.minecraft.text.Text;

public final class ModItemGroups {
	public static final RegistryKey<ItemGroup> SMITHING = RegistryKey.of(RegistryKeys.ITEM_GROUP, Swordsmith.id("smithing"));

	public static void init() {
		Registry.register(Registries.ITEM_GROUP, SMITHING, FabricItemGroup.builder()
				.icon(() -> new ItemStack(ModItems.FORGED_STEEL_SWORD))
				.displayName(Text.translatable("itemGroup.swordsmith.smithing"))
				.build());

		ItemGroupEvents.modifyEntriesEvent(SMITHING).register(entries -> {
			entries.add(ModItems.FORGE);
			entries.add(ModItems.SMITHING_ANVIL);
			entries.add(ModItems.QUENCHING_BARREL);
			entries.add(ModItems.WHETSTONE);
			entries.add(ModItems.SMITHING_HAMMER);
			entries.add(ModItems.SMITHING_TONGS);
			entries.add(ModItems.BELLOWS);
			entries.add(ModItems.IRON_BLOOM);
			entries.add(ModItems.STEEL_BILLET);
			entries.add(ModItems.BLADE_PREFORM);
			entries.add(ModItems.ROUGH_BLADE);
			entries.add(ModItems.CRACKED_BLADE);
			entries.add(ModItems.QUENCHED_BLADE);
			entries.add(ModItems.TEMPERED_BLADE);
			entries.add(ModItems.SHARP_BLADE);
			entries.add(ModItems.SWORD_GUARD);
			entries.add(ModItems.SWORD_GRIP);
			entries.add(ModItems.SWORD_POMMEL);
			entries.add(ModItems.FORGED_STEEL_SWORD);
		});
	}

	private ModItemGroups() {
	}
}
