package dev.shinorange.swordsmith.registry;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.block.QuenchingBarrelBlock;
import dev.shinorange.swordsmith.block.SmithingAnvilBlock;
import dev.shinorange.swordsmith.block.WhetstoneBlock;
import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import dev.shinorange.swordsmith.block.entity.SmithingAnvilBlockEntity;
import dev.shinorange.swordsmith.item.ForgedSwordItem;
import dev.shinorange.swordsmith.item.HeatableItem;
import dev.shinorange.swordsmith.item.HintedBlockItem;
import dev.shinorange.swordsmith.item.HintedItem;
import dev.shinorange.swordsmith.menu.ForgeMenu;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.world.flag.FeatureFlags;
import net.minecraft.world.inventory.MenuType;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Tier;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.SoundType;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

public final class ModRegistry {
	public static final DeferredRegister<Block> BLOCKS = DeferredRegister.create(ForgeRegistries.BLOCKS, Swordsmith.MOD_ID);
	public static final DeferredRegister<Item> ITEMS = DeferredRegister.create(ForgeRegistries.ITEMS, Swordsmith.MOD_ID);
	public static final DeferredRegister<BlockEntityType<?>> BLOCK_ENTITIES = DeferredRegister.create(ForgeRegistries.BLOCK_ENTITY_TYPES, Swordsmith.MOD_ID);
	public static final DeferredRegister<MenuType<?>> MENUS = DeferredRegister.create(ForgeRegistries.MENU_TYPES, Swordsmith.MOD_ID);
	public static final DeferredRegister<CreativeModeTab> TABS = DeferredRegister.create(Registries.CREATIVE_MODE_TAB, Swordsmith.MOD_ID);

	// --- blocks ----------------------------------------------------------
	public static final RegistryObject<ForgeBlock> FORGE = BLOCKS.register("forge",
			() -> new ForgeBlock(BlockBehaviour.Properties.of()
					.strength(3.5f).requiresCorrectToolForDrops().sound(SoundType.STONE)
					.lightLevel(state -> state.getValue(ForgeBlock.LIT) ? 13 : 0)));
	public static final RegistryObject<SmithingAnvilBlock> SMITHING_ANVIL = BLOCKS.register("smithing_anvil",
			() -> new SmithingAnvilBlock(BlockBehaviour.Properties.of()
					.strength(5.0f, 1200.0f).requiresCorrectToolForDrops().sound(SoundType.ANVIL).noOcclusion()));
	public static final RegistryObject<QuenchingBarrelBlock> QUENCHING_BARREL = BLOCKS.register("quenching_barrel",
			() -> new QuenchingBarrelBlock(BlockBehaviour.Properties.of()
					.strength(2.5f).sound(SoundType.WOOD)));
	public static final RegistryObject<WhetstoneBlock> WHETSTONE = BLOCKS.register("whetstone",
			() -> new WhetstoneBlock(BlockBehaviour.Properties.of()
					.strength(3.0f).requiresCorrectToolForDrops().sound(SoundType.STONE).noOcclusion()));

	// --- workpieces, in process order -------------------------------------
	public static final RegistryObject<Item> IRON_BLOOM = workpiece("iron_bloom");
	public static final RegistryObject<Item> STEEL_BILLET = workpiece("steel_billet");
	public static final RegistryObject<Item> BLADE_PREFORM = workpiece("blade_preform");
	public static final RegistryObject<Item> ROUGH_BLADE = workpiece("rough_blade");
	public static final RegistryObject<Item> CRACKED_BLADE = workpiece("cracked_blade");
	public static final RegistryObject<Item> QUENCHED_BLADE = workpiece("quenched_blade");
	public static final RegistryObject<Item> TEMPERED_BLADE = workpiece("tempered_blade");
	public static final RegistryObject<Item> SHARP_BLADE = workpiece("sharp_blade");

	// --- hilt furniture ----------------------------------------------------
	public static final RegistryObject<Item> SWORD_GUARD = ITEMS.register("sword_guard",
			() -> new HintedItem(hint("sword_guard"), new Item.Properties().stacksTo(16)));
	public static final RegistryObject<Item> SWORD_GRIP = ITEMS.register("sword_grip",
			() -> new HintedItem(hint("sword_grip"), new Item.Properties().stacksTo(16)));
	public static final RegistryObject<Item> SWORD_POMMEL = ITEMS.register("sword_pommel",
			() -> new HintedItem(hint("sword_pommel"), new Item.Properties().stacksTo(16)));

	// --- the smith's tools --------------------------------------------------
	public static final RegistryObject<Item> SMITHING_HAMMER = ITEMS.register("smithing_hammer",
			() -> new HintedItem(hint("smithing_hammer"), new Item.Properties().durability(512)));
	public static final RegistryObject<Item> SMITHING_TONGS = ITEMS.register("smithing_tongs",
			() -> new HintedItem(hint("smithing_tongs"), new Item.Properties().durability(256)));
	public static final RegistryObject<Item> BELLOWS = ITEMS.register("bellows",
			() -> new HintedItem(hint("bellows"), new Item.Properties().durability(256)));

	// --- the reward ----------------------------------------------------------
	public static final Tier STEEL_TIER = new Tier() {
		@Override
		public int getUses() {
			return 780;
		}

		@Override
		public float getSpeed() {
			return 6.5f;
		}

		@Override
		public float getAttackDamageBonus() {
			return 3.0f;
		}

		@Override
		public int getLevel() {
			return 2;
		}

		@Override
		public int getEnchantmentValue() {
			return 14;
		}

		@Override
		public Ingredient getRepairIngredient() {
			return Ingredient.of(SHARP_BLADE.get());
		}
	};

	public static final RegistryObject<Item> FORGED_STEEL_SWORD = ITEMS.register("forged_steel_sword",
			() -> new ForgedSwordItem(STEEL_TIER, new Item.Properties().stacksTo(1)));

	// --- block items ----------------------------------------------------------
	public static final RegistryObject<Item> FORGE_ITEM = ITEMS.register("forge",
			() -> new HintedBlockItem(FORGE.get(), "block.swordsmith.forge.hint", new Item.Properties()));
	public static final RegistryObject<Item> SMITHING_ANVIL_ITEM = ITEMS.register("smithing_anvil",
			() -> new HintedBlockItem(SMITHING_ANVIL.get(), "block.swordsmith.smithing_anvil.hint", new Item.Properties()));
	public static final RegistryObject<Item> QUENCHING_BARREL_ITEM = ITEMS.register("quenching_barrel",
			() -> new HintedBlockItem(QUENCHING_BARREL.get(), "block.swordsmith.quenching_barrel.hint", new Item.Properties()));
	public static final RegistryObject<Item> WHETSTONE_ITEM = ITEMS.register("whetstone",
			() -> new HintedBlockItem(WHETSTONE.get(), "block.swordsmith.whetstone.hint", new Item.Properties()));

	// --- block entities / menus / creative tab ---------------------------------
	public static final RegistryObject<BlockEntityType<ForgeBlockEntity>> FORGE_BE = BLOCK_ENTITIES.register("forge",
			() -> BlockEntityType.Builder.of(ForgeBlockEntity::new, FORGE.get()).build(null));
	public static final RegistryObject<BlockEntityType<SmithingAnvilBlockEntity>> SMITHING_ANVIL_BE = BLOCK_ENTITIES.register("smithing_anvil",
			() -> BlockEntityType.Builder.of(SmithingAnvilBlockEntity::new, SMITHING_ANVIL.get()).build(null));

	public static final RegistryObject<MenuType<ForgeMenu>> FORGE_MENU = MENUS.register("forge",
			() -> new MenuType<>(ForgeMenu::new, FeatureFlags.DEFAULT_FLAGS));

	public static final RegistryObject<CreativeModeTab> SMITHING_TAB = TABS.register("smithing",
			() -> CreativeModeTab.builder()
					.title(Component.translatable("itemGroup.swordsmith.smithing"))
					.icon(() -> new ItemStack(FORGED_STEEL_SWORD.get()))
					.displayItems((params, output) -> {
						output.accept(FORGE_ITEM.get());
						output.accept(SMITHING_ANVIL_ITEM.get());
						output.accept(QUENCHING_BARREL_ITEM.get());
						output.accept(WHETSTONE_ITEM.get());
						output.accept(SMITHING_HAMMER.get());
						output.accept(SMITHING_TONGS.get());
						output.accept(BELLOWS.get());
						output.accept(IRON_BLOOM.get());
						output.accept(STEEL_BILLET.get());
						output.accept(BLADE_PREFORM.get());
						output.accept(ROUGH_BLADE.get());
						output.accept(CRACKED_BLADE.get());
						output.accept(QUENCHED_BLADE.get());
						output.accept(TEMPERED_BLADE.get());
						output.accept(SHARP_BLADE.get());
						output.accept(SWORD_GUARD.get());
						output.accept(SWORD_GRIP.get());
						output.accept(SWORD_POMMEL.get());
						output.accept(FORGED_STEEL_SWORD.get());
					})
					.build());

	private static RegistryObject<Item> workpiece(String name) {
		return ITEMS.register(name,
				() -> new HeatableItem(hint(name), new Item.Properties().stacksTo(1).fireResistant()));
	}

	private static String hint(String name) {
		return "item.swordsmith." + name + ".hint";
	}

	public static void register(IEventBus modBus) {
		BLOCKS.register(modBus);
		ITEMS.register(modBus);
		BLOCK_ENTITIES.register(modBus);
		MENUS.register(modBus);
		TABS.register(modBus);
	}

	private ModRegistry() {
	}
}
