package dev.shinorange.swordsmith.block;

import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.util.RandomSource;
import net.minecraft.world.Containers;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.ItemUtils;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BaseEntityBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraftforge.network.NetworkHooks;

/**
 * The charcoal forge. Coal stockpiles in the fuel slot, flint and steel
 * lights a ~300 C banked fire, and the bellows drive it toward 1280 C.
 * Bare-handed right-click opens the menu; tongs pull the workpiece directly.
 */
public class ForgeBlock extends BaseEntityBlock {
	public static final BooleanProperty LIT = BlockStateProperties.LIT;

	public ForgeBlock(Properties properties) {
		super(properties);
		this.registerDefaultState(this.stateDefinition.any().setValue(LIT, false));
	}

	@Override
	protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
		builder.add(LIT);
	}

	@Override
	public RenderShape getRenderShape(BlockState state) {
		return RenderShape.MODEL;
	}

	@Override
	public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
		return new ForgeBlockEntity(pos, state);
	}

	@Override
	public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
		return level.isClientSide ? null : createTickerHelper(type, ModRegistry.FORGE_BE.get(), ForgeBlockEntity::serverTick);
	}

	@Override
	public InteractionResult use(BlockState state, Level level, BlockPos pos, Player player, InteractionHand hand, BlockHitResult hit) {
		if (!(level.getBlockEntity(pos) instanceof ForgeBlockEntity forge)) {
			return InteractionResult.PASS;
		}
		ItemStack stack = player.getItemInHand(hand);
		boolean lit = state.getValue(LIT);

		// Stoke the fire with coal or charcoal.
		if (stack.is(Items.COAL) || stack.is(Items.CHARCOAL)) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			if (forge.addFuelItem(stack)) {
				if (!player.isCreative()) {
					stack.shrink(1);
				}
				level.playSound(null, pos, SoundEvents.GRAVEL_PLACE, SoundSource.BLOCKS, 0.7f, 0.8f);
			} else {
				player.displayClientMessage(Component.translatable("msg.swordsmith.fuel_full"), true);
			}
			return InteractionResult.CONSUME;
		}

		// Light it.
		if (stack.is(Items.FLINT_AND_STEEL)) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			if (lit) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.already_lit"), true);
			} else if (forge.hasFuel()) {
				level.setBlock(pos, state.setValue(LIT, true), Block.UPDATE_ALL);
				stack.hurtAndBreak(1, player, p -> p.broadcastBreakEvent(hand));
				level.playSound(null, pos, SoundEvents.FLINTANDSTEEL_USE, SoundSource.BLOCKS, 1.0f, 1.0f);
			} else {
				player.displayClientMessage(Component.translatable("msg.swordsmith.need_fuel"), true);
			}
			return InteractionResult.CONSUME;
		}

		// Pump air into the fire.
		if (stack.is(ModRegistry.BELLOWS.get())) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			if (!lit) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.need_lit"), true);
				return InteractionResult.CONSUME;
			}
			forge.pump();
			stack.hurtAndBreak(1, player, p -> p.broadcastBreakEvent(hand));
			player.getCooldowns().addCooldown(ModRegistry.BELLOWS.get(), 10);
			level.playSound(null, pos, SoundEvents.HORSE_BREATHE, SoundSource.BLOCKS, 0.8f, 0.5f);
			if (level instanceof ServerLevel serverLevel) {
				serverLevel.sendParticles(ParticleTypes.FLAME,
						pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 6, 0.25, 0.05, 0.25, 0.01);
			}
			return InteractionResult.CONSUME;
		}

		// Douse the fire.
		if (stack.is(Items.WATER_BUCKET) && lit) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			level.setBlock(pos, state.setValue(LIT, false), Block.UPDATE_ALL);
			player.setItemInHand(hand, ItemUtils.createFilledResult(stack, player, new ItemStack(Items.BUCKET)));
			level.playSound(null, pos, SoundEvents.FIRE_EXTINGUISH, SoundSource.BLOCKS, 1.0f, 1.0f);
			if (level instanceof ServerLevel serverLevel) {
				serverLevel.sendParticles(ParticleTypes.CLOUD,
						pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5, 8, 0.25, 0.1, 0.25, 0.02);
			}
			return InteractionResult.CONSUME;
		}

		// Lay a workpiece in the coals.
		if (Smithing.isHeatable(stack)) {
			if (!forge.getWorkpiece().isEmpty()) {
				if (!level.isClientSide) {
					player.displayClientMessage(Component.translatable("msg.swordsmith.forge_occupied"), true);
				}
				return InteractionResult.sidedSuccess(level.isClientSide);
			}
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			ItemStack one = stack.copyWithCount(1);
			if (!player.isCreative()) {
				stack.shrink(1);
			}
			forge.insertWorkpiece(one);
			level.playSound(null, pos, SoundEvents.ITEM_FRAME_ADD_ITEM, SoundSource.BLOCKS, 0.9f, 0.9f);
			return InteractionResult.CONSUME;
		}

		// Take the workpiece out with tongs, without opening the menu.
		if (stack.is(ModRegistry.SMITHING_TONGS.get())) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			if (forge.getWorkpiece().isEmpty()) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.forge_empty"), true);
			} else {
				ItemStack out = forge.takeWorkpiece();
				if (!player.getInventory().add(out)) {
					player.drop(out, false);
				}
				level.playSound(null, pos, SoundEvents.ITEM_FRAME_REMOVE_ITEM, SoundSource.BLOCKS, 0.9f, 0.9f);
			}
			return InteractionResult.CONSUME;
		}

		// Bare hand (or anything unhandled that is not a block): open the menu.
		if (stack.isEmpty()) {
			if (player instanceof ServerPlayer serverPlayer) {
				NetworkHooks.openScreen(serverPlayer, forge);
			}
			return InteractionResult.sidedSuccess(level.isClientSide);
		}

		return InteractionResult.PASS;
	}

	@Override
	public void onRemove(BlockState state, Level level, BlockPos pos, BlockState newState, boolean moved) {
		if (!state.is(newState.getBlock()) && level.getBlockEntity(pos) instanceof ForgeBlockEntity forge) {
			forge.stampHeat(forge.getWorkpiece());
			Containers.dropContents(level, pos, forge);
		}
		super.onRemove(state, level, pos, newState, moved);
	}

	@Override
	public void animateTick(BlockState state, Level level, BlockPos pos, RandomSource random) {
		if (!state.getValue(LIT)) {
			return;
		}
		for (int i = 0; i < 2; i++) {
			double x = pos.getX() + 0.3 + random.nextDouble() * 0.4;
			double y = pos.getY() + 1.0 + random.nextDouble() * 0.15;
			double z = pos.getZ() + 0.3 + random.nextDouble() * 0.4;
			level.addParticle(ParticleTypes.SMALL_FLAME, x, y, z, 0.0, 0.02, 0.0);
		}
		if (random.nextInt(4) == 0) {
			level.addParticle(ParticleTypes.SMOKE,
					pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 0.0, 0.05, 0.0);
		}
		if (random.nextInt(8) == 0) {
			level.playLocalSound(pos.getX() + 0.5, pos.getY() + 0.5, pos.getZ() + 0.5,
					SoundEvents.CAMPFIRE_CRACKLE, SoundSource.BLOCKS,
					0.6f + random.nextFloat(), random.nextFloat() * 0.7f + 0.6f, false);
		}
	}
}
