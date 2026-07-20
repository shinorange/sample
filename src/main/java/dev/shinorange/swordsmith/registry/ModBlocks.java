package dev.shinorange.swordsmith.registry;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.block.QuenchingBarrelBlock;
import dev.shinorange.swordsmith.block.SmithingAnvilBlock;
import dev.shinorange.swordsmith.block.WhetstoneBlock;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.sound.BlockSoundGroup;

public final class ModBlocks {
	public static final ForgeBlock FORGE = register("forge", new ForgeBlock(AbstractBlock.Settings.create()
			.strength(3.5f)
			.requiresTool()
			.sounds(BlockSoundGroup.STONE)
			.luminance(state -> state.get(ForgeBlock.LIT) ? 13 : 0)));

	public static final SmithingAnvilBlock SMITHING_ANVIL = register("smithing_anvil", new SmithingAnvilBlock(AbstractBlock.Settings.create()
			.strength(5.0f, 1200.0f)
			.requiresTool()
			.sounds(BlockSoundGroup.ANVIL)
			.nonOpaque()));

	public static final QuenchingBarrelBlock QUENCHING_BARREL = register("quenching_barrel", new QuenchingBarrelBlock(AbstractBlock.Settings.create()
			.strength(2.5f)
			.sounds(BlockSoundGroup.WOOD)));

	public static final WhetstoneBlock WHETSTONE = register("whetstone", new WhetstoneBlock(AbstractBlock.Settings.create()
			.strength(3.0f)
			.requiresTool()
			.sounds(BlockSoundGroup.STONE)
			.nonOpaque()));

	private static <T extends Block> T register(String name, T block) {
		return Registry.register(Registries.BLOCK, Swordsmith.id(name), block);
	}

	public static void init() {
	}

	private ModBlocks() {
	}
}
