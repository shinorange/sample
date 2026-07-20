package dev.shinorange.swordsmith.block;

import com.mojang.serialization.MapCodec;
import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModBlockEntities;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.block.Block;
import net.minecraft.block.BlockRenderType;
import net.minecraft.block.BlockState;
import net.minecraft.block.BlockWithEntity;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.block.entity.BlockEntityTicker;
import net.minecraft.block.entity.BlockEntityType;
import net.minecraft.entity.EquipmentSlot;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.item.ItemUsage;
import net.minecraft.item.Items;
import net.minecraft.particle.ParticleTypes;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.sound.SoundCategory;
import net.minecraft.sound.SoundEvents;
import net.minecraft.state.StateManager;
import net.minecraft.state.property.BooleanProperty;
import net.minecraft.state.property.Properties;
import net.minecraft.text.Text;
import net.minecraft.util.ActionResult;
import net.minecraft.util.Hand;
import net.minecraft.util.ItemActionResult;
import net.minecraft.util.ItemScatterer;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.random.Random;
import net.minecraft.world.World;

/**
 * The charcoal forge. Feed it coal or charcoal, light it with flint and steel,
 * pump the bellows to raise the fire towards white heat, and lay a workpiece
 * in the coals. It smelts raw iron into a bloom at high heat and tempers a
 * quenched blade at low heat — watch it, or you will anneal your hard work.
 */
public class ForgeBlock extends BlockWithEntity {
	public static final MapCodec<ForgeBlock> CODEC = createCodec(ForgeBlock::new);
	public static final BooleanProperty LIT = Properties.LIT;

	public ForgeBlock(Settings settings) {
		super(settings);
		this.setDefaultState(this.getDefaultState().with(LIT, false));
	}

	@Override
	protected MapCodec<? extends BlockWithEntity> getCodec() {
		return CODEC;
	}

	@Override
	protected void appendProperties(StateManager.Builder<Block, BlockState> builder) {
		builder.add(LIT);
	}

	@Override
	protected BlockRenderType getRenderType(BlockState state) {
		return BlockRenderType.MODEL;
	}

	@Override
	public BlockEntity createBlockEntity(BlockPos pos, BlockState state) {
		return new ForgeBlockEntity(pos, state);
	}

	@Override
	public <T extends BlockEntity> BlockEntityTicker<T> getTicker(World world, BlockState state, BlockEntityType<T> type) {
		return world.isClient ? null : validateTicker(type, ModBlockEntities.FORGE, ForgeBlockEntity::serverTick);
	}

	@Override
	protected ItemActionResult onUseWithItem(ItemStack stack, BlockState state, World world, BlockPos pos, PlayerEntity player, Hand hand, BlockHitResult hit) {
		if (!(world.getBlockEntity(pos) instanceof ForgeBlockEntity forge)) {
			return ItemActionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
		}
		boolean lit = state.get(LIT);

		// Stoke the fire with coal or charcoal.
		if (stack.isOf(Items.COAL) || stack.isOf(Items.CHARCOAL)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			if (forge.addFuelItem(stack)) {
				if (!player.isCreative()) {
					stack.decrement(1);
				}
				world.playSound(null, pos, SoundEvents.BLOCK_GRAVEL_PLACE, SoundCategory.BLOCKS, 0.7f, 0.8f);
			} else {
				player.sendMessage(Text.translatable("msg.swordsmith.fuel_full"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		// Light it.
		if (stack.isOf(Items.FLINT_AND_STEEL)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			if (lit) {
				player.sendMessage(Text.translatable("msg.swordsmith.already_lit"), true);
			} else if (forge.hasFuel()) {
				world.setBlockState(pos, state.with(LIT, true), Block.NOTIFY_ALL);
				stack.damage(1, player, hand == Hand.MAIN_HAND ? EquipmentSlot.MAINHAND : EquipmentSlot.OFFHAND);
				world.playSound(null, pos, SoundEvents.ITEM_FLINTANDSTEEL_USE, SoundCategory.BLOCKS, 1.0f, 1.0f);
			} else {
				player.sendMessage(Text.translatable("msg.swordsmith.need_fuel"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		// Pump air into the fire.
		if (stack.isOf(ModItems.BELLOWS)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			if (!lit) {
				player.sendMessage(Text.translatable("msg.swordsmith.need_lit"), true);
				return ItemActionResult.SUCCESS;
			}
			forge.pump();
			stack.damage(1, player, hand == Hand.MAIN_HAND ? EquipmentSlot.MAINHAND : EquipmentSlot.OFFHAND);
			player.getItemCooldownManager().set(ModItems.BELLOWS, 10);
			world.playSound(null, pos, SoundEvents.ENTITY_HORSE_BREATHE, SoundCategory.BLOCKS, 0.8f, 0.5f);
			if (world instanceof ServerWorld serverWorld) {
				serverWorld.spawnParticles(ParticleTypes.FLAME,
						pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 6, 0.25, 0.05, 0.25, 0.01);
			}
			return ItemActionResult.SUCCESS;
		}

		// Douse the fire.
		if (stack.isOf(Items.WATER_BUCKET) && lit) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			world.setBlockState(pos, state.with(LIT, false), Block.NOTIFY_ALL);
			player.setStackInHand(hand, ItemUsage.exchangeStack(stack, player, new ItemStack(Items.BUCKET)));
			world.playSound(null, pos, SoundEvents.BLOCK_FIRE_EXTINGUISH, SoundCategory.BLOCKS, 1.0f, 1.0f);
			if (world instanceof ServerWorld serverWorld) {
				serverWorld.spawnParticles(ParticleTypes.CLOUD,
						pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5, 8, 0.25, 0.1, 0.25, 0.02);
			}
			return ItemActionResult.SUCCESS;
		}

		// Lay a workpiece in the coals.
		if (Smithing.isHeatable(stack)) {
			if (!forge.getWorkpiece().isEmpty()) {
				if (!world.isClient) {
					player.sendMessage(Text.translatable("msg.swordsmith.forge_occupied"), true);
				}
				return ItemActionResult.SUCCESS;
			}
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			ItemStack one = stack.copyWithCount(1);
			if (!player.isCreative()) {
				stack.decrement(1);
			}
			forge.insertWorkpiece(one);
			world.playSound(null, pos, SoundEvents.ENTITY_ITEM_FRAME_ADD_ITEM, SoundCategory.BLOCKS, 0.9f, 0.9f);
			return ItemActionResult.SUCCESS;
		}

		// Take the workpiece out with tongs, without opening the menu.
		if (stack.isOf(ModItems.SMITHING_TONGS)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			if (forge.getWorkpiece().isEmpty()) {
				player.sendMessage(Text.translatable("msg.swordsmith.forge_empty"), true);
			} else {
				player.getInventory().offerOrDrop(forge.takeWorkpiece());
				world.playSound(null, pos, SoundEvents.ENTITY_ITEM_FRAME_REMOVE_ITEM, SoundCategory.BLOCKS, 0.9f, 0.9f);
			}
			return ItemActionResult.SUCCESS;
		}

		return ItemActionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
	}

	@Override
	protected ActionResult onUse(BlockState state, World world, BlockPos pos, PlayerEntity player, BlockHitResult hit) {
		if (!(world.getBlockEntity(pos) instanceof ForgeBlockEntity forge)) {
			return ActionResult.PASS;
		}
		if (!world.isClient) {
			player.openHandledScreen(forge);
		}
		return ActionResult.SUCCESS;
	}

	@Override
	protected void onStateReplaced(BlockState state, World world, BlockPos pos, BlockState newState, boolean moved) {
		if (!state.isOf(newState.getBlock()) && world.getBlockEntity(pos) instanceof ForgeBlockEntity forge) {
			forge.stampHeat(forge.getWorkpiece());
			ItemScatterer.spawn(world, pos, forge);
			forge.clear();
		}
		super.onStateReplaced(state, world, pos, newState, moved);
	}

	@Override
	public void randomDisplayTick(BlockState state, World world, BlockPos pos, Random random) {
		if (!state.get(LIT)) {
			return;
		}
		for (int i = 0; i < 2; i++) {
			double x = pos.getX() + 0.3 + random.nextDouble() * 0.4;
			double y = pos.getY() + 1.0 + random.nextDouble() * 0.15;
			double z = pos.getZ() + 0.3 + random.nextDouble() * 0.4;
			world.addParticle(ParticleTypes.SMALL_FLAME, x, y, z, 0.0, 0.02, 0.0);
		}
		if (random.nextInt(4) == 0) {
			world.addParticle(ParticleTypes.SMOKE,
					pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 0.0, 0.05, 0.0);
		}
		if (random.nextInt(8) == 0) {
			world.playSound(pos.getX() + 0.5, pos.getY() + 0.5, pos.getZ() + 0.5,
					SoundEvents.BLOCK_CAMPFIRE_CRACKLE, SoundCategory.BLOCKS,
					0.6f + random.nextFloat(), random.nextFloat() * 0.7f + 0.6f, false);
		}
	}
}
