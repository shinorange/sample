package dev.shinorange.swordsmith.registry;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import dev.shinorange.swordsmith.block.entity.SmithingAnvilBlockEntity;
import net.minecraft.block.entity.BlockEntityType;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;

public final class ModBlockEntities {
	public static final BlockEntityType<ForgeBlockEntity> FORGE = Registry.register(
			Registries.BLOCK_ENTITY_TYPE, Swordsmith.id("forge"),
			BlockEntityType.Builder.create(ForgeBlockEntity::new, ModBlocks.FORGE).build(null));

	public static final BlockEntityType<SmithingAnvilBlockEntity> SMITHING_ANVIL = Registry.register(
			Registries.BLOCK_ENTITY_TYPE, Swordsmith.id("smithing_anvil"),
			BlockEntityType.Builder.create(SmithingAnvilBlockEntity::new, ModBlocks.SMITHING_ANVIL).build(null));

	public static void init() {
	}

	private ModBlockEntities() {
	}
}
