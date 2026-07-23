package dev.shinorange.swordsmith.block;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.item.HeatableItem;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * The sharpening wheel. Only a cold, tempered blade takes an edge here —
 * grinding hot steel would ruin the temper.
 */
public class WhetstoneBlock extends Block {
	public static final DirectionProperty FACING = BlockStateProperties.HORIZONTAL_FACING;

	private static final VoxelShape BASE = Block.box(0, 0, 0, 16, 7, 16);
	private static final VoxelShape NS_WHEEL = Block.box(6, 5, 2, 10, 15, 14);
	private static final VoxelShape EW_WHEEL = Block.box(2, 5, 6, 14, 15, 10);
	private static final VoxelShape NS_SHAPE = Shapes.or(BASE, NS_WHEEL);
	private static final VoxelShape EW_SHAPE = Shapes.or(BASE, EW_WHEEL);

	public WhetstoneBlock(Properties properties) {
		super(properties);
		this.registerDefaultState(this.stateDefinition.any().setValue(FACING, Direction.NORTH));
	}

	@Override
	protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
		builder.add(FACING);
	}

	@Override
	public BlockState getStateForPlacement(BlockPlaceContext context) {
		return this.defaultBlockState().setValue(FACING, context.getHorizontalDirection().getOpposite());
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
		return state.getValue(FACING).getAxis() == Direction.Axis.Z ? NS_SHAPE : EW_SHAPE;
	}

	@Override
	public InteractionResult use(BlockState state, Level level, BlockPos pos, Player player, InteractionHand hand, BlockHitResult hit) {
		ItemStack stack = player.getItemInHand(hand);

		if (stack.is(ModRegistry.TEMPERED_BLADE.get())) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			float temp = Heat.current(level, stack);
			if (temp > Heat.COLD_WORK_MAX) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.grind_hot"), true);
				return InteractionResult.CONSUME;
			}
			int progress = (stack.getTag() == null ? 0 : stack.getTag().getInt(Quality.GRIND_KEY)) + 1;
			player.getCooldowns().addCooldown(ModRegistry.TEMPERED_BLADE.get(), 5);
			if (progress >= Heat.GRIND_USES) {
				ItemStack sharp = new ItemStack(ModRegistry.SHARP_BLADE.get());
				Quality.carry(stack, sharp);
				player.setItemInHand(hand, sharp);
				player.displayClientMessage(Component.translatable("msg.swordsmith.stage_complete", sharp.getHoverName()), true);
				level.playSound(null, pos, SoundEvents.EXPERIENCE_ORB_PICKUP, SoundSource.BLOCKS, 0.6f, 1.3f);
			} else {
				stack.getOrCreateTag().putInt(Quality.GRIND_KEY, progress);
				player.displayClientMessage(Component.translatable("msg.swordsmith.grind_progress", progress, Heat.GRIND_USES), true);
			}
			level.playSound(null, pos, SoundEvents.GRINDSTONE_USE, SoundSource.BLOCKS, 0.6f,
					0.9f + level.getRandom().nextFloat() * 0.2f);
			if (level instanceof ServerLevel serverLevel) {
				serverLevel.sendParticles(ParticleTypes.CRIT,
						pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5, 5, 0.2, 0.1, 0.2, 0.1);
			}
			return InteractionResult.CONSUME;
		}

		if (stack.is(ModRegistry.SHARP_BLADE.get())) {
			if (!level.isClientSide) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.grind_already_sharp"), true);
			}
			return InteractionResult.sidedSuccess(level.isClientSide);
		}

		if (stack.getItem() instanceof HeatableItem) {
			if (!level.isClientSide) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.grind_wrong"), true);
			}
			return InteractionResult.sidedSuccess(level.isClientSide);
		}

		return InteractionResult.PASS;
	}
}
