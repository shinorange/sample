package dev.shinorange.swordsmith.block;

import dev.shinorange.swordsmith.block.entity.SmithingAnvilBlockEntity;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.Containers;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BaseEntityBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * The smith's anvil: hammer work at forging heat (720 C+, perfect at
 * 900-1150 C) and the final cold hilt assembly, peened tight in three taps.
 */
public class SmithingAnvilBlock extends BaseEntityBlock {
	public static final DirectionProperty FACING = BlockStateProperties.HORIZONTAL_FACING;

	private static final VoxelShape BASE = Block.box(2, 0, 2, 14, 4, 14);
	private static final VoxelShape X_STEM = Block.box(4, 4, 6, 12, 10, 10);
	private static final VoxelShape X_FACE = Block.box(0, 10, 3, 16, 16, 13);
	private static final VoxelShape Z_STEM = Block.box(6, 4, 4, 10, 10, 12);
	private static final VoxelShape Z_FACE = Block.box(3, 10, 0, 13, 16, 16);
	private static final VoxelShape X_SHAPE = Shapes.or(BASE, X_STEM, X_FACE);
	private static final VoxelShape Z_SHAPE = Shapes.or(BASE, Z_STEM, Z_FACE);

	public SmithingAnvilBlock(Properties properties) {
		super(properties);
		this.registerDefaultState(this.stateDefinition.any().setValue(FACING, Direction.NORTH));
	}

	@Override
	protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
		builder.add(FACING);
	}

	@Override
	public BlockState getStateForPlacement(BlockPlaceContext context) {
		return this.defaultBlockState().setValue(FACING, context.getHorizontalDirection().getClockWise());
	}

	@Override
	public BlockState rotate(BlockState state, Rotation rotation) {
		return state.setValue(FACING, rotation.rotate(state.getValue(FACING)));
	}

	@Override
	public BlockState mirror(BlockState state, Mirror mirror) {
		return state.rotate(mirror.getRotation(state.getValue(FACING)));
	}

	@Override
	public VoxelShape getShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {
		return state.getValue(FACING).getAxis() == Direction.Axis.X ? X_SHAPE : Z_SHAPE;
	}

	@Override
	public RenderShape getRenderShape(BlockState state) {
		return RenderShape.MODEL;
	}

	@Override
	public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
		return new SmithingAnvilBlockEntity(pos, state);
	}

	@Override
	public InteractionResult use(BlockState state, Level level, BlockPos pos, Player player, InteractionHand hand, BlockHitResult hit) {
		if (!(level.getBlockEntity(pos) instanceof SmithingAnvilBlockEntity anvil)) {
			return InteractionResult.PASS;
		}
		ItemStack stack = player.getItemInHand(hand);

		if (stack.is(ModRegistry.SMITHING_HAMMER.get())) {
			if (level instanceof ServerLevel serverLevel) {
				strike(serverLevel, pos, player, stack, hand, anvil);
			}
			return InteractionResult.sidedSuccess(level.isClientSide);
		}

		if (stack.is(ModRegistry.SWORD_GUARD.get()) || stack.is(ModRegistry.SWORD_GRIP.get())
				|| stack.is(ModRegistry.SWORD_POMMEL.get())) {
			if (level instanceof ServerLevel serverLevel) {
				attach(serverLevel, pos, player, stack, anvil);
			}
			return InteractionResult.sidedSuccess(level.isClientSide);
		}

		if (Smithing.isHeatable(stack) && anvil.getWorkpiece().isEmpty()) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			ItemStack one = stack.copyWithCount(1);
			if (!player.isCreative()) {
				stack.shrink(1);
			}
			anvil.setWorkpiece(one);
			level.playSound(null, pos, SoundEvents.ANVIL_PLACE, SoundSource.BLOCKS, 0.4f, 1.4f);
			return InteractionResult.CONSUME;
		}

		if (stack.is(ModRegistry.SMITHING_TONGS.get()) || stack.isEmpty()) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			takeEverything(level, pos, player, anvil);
			return InteractionResult.CONSUME;
		}

		return InteractionResult.PASS;
	}

	private void takeEverything(Level level, BlockPos pos, Player player, SmithingAnvilBlockEntity anvil) {
		if (anvil.getWorkpiece().isEmpty()) {
			player.displayClientMessage(Component.translatable("msg.swordsmith.anvil_empty"), true);
			return;
		}
		for (ItemStack stack : anvil.removeEverything()) {
			if (!player.getInventory().add(stack)) {
				player.drop(stack, false);
			}
		}
		level.playSound(null, pos, SoundEvents.ITEM_FRAME_REMOVE_ITEM, SoundSource.BLOCKS, 0.9f, 0.9f);
	}

	private void strike(ServerLevel level, BlockPos pos, Player player, ItemStack hammer, InteractionHand hand, SmithingAnvilBlockEntity anvil) {
		ItemStack workpiece = anvil.getWorkpiece();
		if (workpiece.isEmpty()) {
			player.displayClientMessage(Component.translatable("msg.swordsmith.anvil_empty"), true);
			return;
		}

		if (anvil.isAwaitingPeen()) {
			anvil.addPeenStrike();
			hammer.hurtAndBreak(1, player, p -> p.broadcastBreakEvent(hand));
			level.playSound(null, pos, SoundEvents.ANVIL_USE, SoundSource.BLOCKS, 0.8f, 1.4f);
			spawnSparks(level, pos, 3, 0);
			if (anvil.getPeenStrikes() >= Heat.PEEN_STRIKES) {
				anvil.finishSword();
				player.displayClientMessage(Component.translatable("msg.swordsmith.sword_finished"), true);
				level.playSound(null, pos, SoundEvents.PLAYER_LEVELUP, SoundSource.BLOCKS, 0.6f, 1.0f);
			} else {
				player.displayClientMessage(Component.translatable("msg.swordsmith.peen_ready",
						Heat.PEEN_STRIKES - anvil.getPeenStrikes()), true);
			}
			return;
		}

		if (workpiece.is(ModRegistry.SHARP_BLADE.get())) {
			player.displayClientMessage(Component.translatable(anvil.nextAssemblyStepKey()), true);
			return;
		}

		Smithing.Forging step = Smithing.forgingOf(workpiece.getItem());
		if (step == null) {
			player.displayClientMessage(Component.translatable("msg.swordsmith.not_forgeable"), true);
			return;
		}

		float temp = Heat.current(level, workpiece);
		if (temp < Heat.FORGING_MIN) {
			player.displayClientMessage(Component.translatable("msg.swordsmith.too_cold"), true);
			level.playSound(null, pos, SoundEvents.ANVIL_HIT, SoundSource.BLOCKS, 0.5f, 0.6f);
			return;
		}

		float score = Quality.strikeScore(temp);
		boolean perfect = score >= 1.0f;
		Quality.addStrike(workpiece, score);

		anvil.addStrike();
		Heat.set(level, workpiece, temp - Heat.STRIKE_COOLING);
		anvil.markWorkpieceChanged();
		hammer.hurtAndBreak(1, player, p -> p.broadcastBreakEvent(hand));
		level.playSound(null, pos, SoundEvents.ANVIL_USE, SoundSource.BLOCKS, 0.7f,
				(perfect ? 1.05f : 0.9f) + level.getRandom().nextFloat() * 0.2f);
		spawnSparks(level, pos, perfect ? 14 : 8, perfect ? 3 : 2);

		if (anvil.getStrikes() >= step.strikes()) {
			ItemStack next = new ItemStack(step.output());
			Quality.carry(workpiece, next);
			Heat.set(level, next, Math.max(Heat.AMBIENT, temp - Heat.STRIKE_COOLING));
			anvil.setWorkpiece(next);
			anvil.resetStrikes();
			player.displayClientMessage(Component.translatable("msg.swordsmith.stage_complete", next.getHoverName()), true);
			level.playSound(null, pos, SoundEvents.EXPERIENCE_ORB_PICKUP, SoundSource.BLOCKS, 0.6f, 1.1f);
		} else {
			player.displayClientMessage(Component.translatable(
					perfect ? "msg.swordsmith.forging_progress_perfect" : "msg.swordsmith.forging_progress",
					anvil.getStrikes(), step.strikes()), true);
		}
	}

	private void attach(ServerLevel level, BlockPos pos, Player player, ItemStack stack, SmithingAnvilBlockEntity anvil) {
		ItemStack workpiece = anvil.getWorkpiece();
		if (!workpiece.is(ModRegistry.SHARP_BLADE.get())) {
			player.displayClientMessage(Component.translatable("msg.swordsmith.need_sharp_blade"), true);
			return;
		}
		if (Heat.current(level, workpiece) > Heat.COLD_WORK_MAX) {
			player.displayClientMessage(Component.translatable("msg.swordsmith.attach_hot"), true);
			return;
		}

		boolean attached = false;
		if (stack.is(ModRegistry.SWORD_GUARD.get()) && !anvil.hasGuard()) {
			anvil.setGuard();
			attached = true;
		} else if (stack.is(ModRegistry.SWORD_GRIP.get()) && anvil.hasGuard() && !anvil.hasGrip()) {
			anvil.setGrip();
			attached = true;
		} else if (stack.is(ModRegistry.SWORD_POMMEL.get()) && anvil.hasGrip() && !anvil.hasPommel()) {
			anvil.setPommel();
			attached = true;
		}

		if (attached) {
			if (!player.isCreative()) {
				stack.shrink(1);
			}
			level.playSound(null, pos, SoundEvents.ITEM_FRAME_ADD_ITEM, SoundSource.BLOCKS, 1.0f, 1.1f);
		}
		player.displayClientMessage(Component.translatable(anvil.nextAssemblyStepKey()), true);
	}

	private void spawnSparks(ServerLevel level, BlockPos pos, int crit, int lava) {
		double x = pos.getX() + 0.5;
		double y = pos.getY() + 1.1;
		double z = pos.getZ() + 0.5;
		if (crit > 0) {
			level.sendParticles(ParticleTypes.CRIT, x, y, z, crit, 0.25, 0.1, 0.25, 0.15);
		}
		if (lava > 0) {
			level.sendParticles(ParticleTypes.LAVA, x, y, z, lava, 0.15, 0.05, 0.15, 0.0);
		}
	}

	@Override
	public void onRemove(BlockState state, Level level, BlockPos pos, BlockState newState, boolean moved) {
		if (!state.is(newState.getBlock()) && level.getBlockEntity(pos) instanceof SmithingAnvilBlockEntity anvil) {
			for (ItemStack stack : anvil.removeEverything()) {
				Containers.dropItemStack(level, pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5, stack);
			}
		}
		super.onRemove(state, level, pos, newState, moved);
	}
}
