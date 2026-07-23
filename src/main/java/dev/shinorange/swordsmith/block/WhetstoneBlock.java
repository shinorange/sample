package dev.shinorange.swordsmith.block;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.item.HeatableItem;
import dev.shinorange.swordsmith.registry.ModComponents;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.ShapeContext;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.ItemPlacementContext;
import net.minecraft.item.ItemStack;
import net.minecraft.particle.ParticleTypes;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.sound.SoundCategory;
import net.minecraft.sound.SoundEvents;
import net.minecraft.state.StateManager;
import net.minecraft.state.property.DirectionProperty;
import net.minecraft.state.property.Properties;
import net.minecraft.text.Text;
import net.minecraft.util.BlockMirror;
import net.minecraft.util.BlockRotation;
import net.minecraft.util.Hand;
import net.minecraft.util.ItemActionResult;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.util.shape.VoxelShape;
import net.minecraft.util.shape.VoxelShapes;
import net.minecraft.world.BlockView;
import net.minecraft.world.World;

/**
 * The sharpening wheel. A tempered blade — and only a tempered blade — is
 * ground here, pass after pass, until it takes a real edge. Grinding a hot
 * blade would ruin the temper, so let it cool first.
 */
public class WhetstoneBlock extends Block {
	public static final DirectionProperty FACING = Properties.HORIZONTAL_FACING;

	private static final VoxelShape BASE = Block.createCuboidShape(0, 0, 0, 16, 7, 16);
	private static final VoxelShape NS_WHEEL = Block.createCuboidShape(6, 5, 2, 10, 15, 14);
	private static final VoxelShape EW_WHEEL = Block.createCuboidShape(2, 5, 6, 14, 15, 10);
	private static final VoxelShape NS_SHAPE = VoxelShapes.union(BASE, NS_WHEEL);
	private static final VoxelShape EW_SHAPE = VoxelShapes.union(BASE, EW_WHEEL);

	public WhetstoneBlock(Settings settings) {
		super(settings);
		this.setDefaultState(this.getDefaultState().with(FACING, Direction.NORTH));
	}

	@Override
	protected void appendProperties(StateManager.Builder<Block, BlockState> builder) {
		builder.add(FACING);
	}

	@Override
	public BlockState getPlacementState(ItemPlacementContext ctx) {
		return this.getDefaultState().with(FACING, ctx.getHorizontalPlayerFacing().getOpposite());
	}

	@Override
	protected BlockState rotate(BlockState state, BlockRotation rotation) {
		return state.with(FACING, rotation.rotate(state.get(FACING)));
	}

	@Override
	protected BlockState mirror(BlockState state, BlockMirror mirror) {
		return state.rotate(mirror.getRotation(state.get(FACING)));
	}

	@Override
	protected VoxelShape getOutlineShape(BlockState state, BlockView world, BlockPos pos, ShapeContext context) {
		return state.get(FACING).getAxis() == Direction.Axis.Z ? NS_SHAPE : EW_SHAPE;
	}

	@Override
	protected ItemActionResult onUseWithItem(ItemStack stack, BlockState state, World world, BlockPos pos, PlayerEntity player, Hand hand, BlockHitResult hit) {
		if (stack.isOf(ModItems.TEMPERED_BLADE)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			float temp = Heat.current(world, stack);
			if (temp > Heat.COLD_WORK_MAX) {
				player.sendMessage(Text.translatable("msg.swordsmith.grind_hot"), true);
				return ItemActionResult.SUCCESS;
			}
			int progress = stack.getOrDefault(ModComponents.GRIND_PROGRESS, 0) + 1;
			player.getItemCooldownManager().set(ModItems.TEMPERED_BLADE, 5);
			if (progress >= Heat.GRIND_USES) {
				ItemStack sharp = new ItemStack(ModItems.SHARP_BLADE);
				Quality.carry(stack, sharp);
				player.setStackInHand(hand, sharp);
				player.sendMessage(Text.translatable("msg.swordsmith.stage_complete", sharp.getName()), true);
				world.playSound(null, pos, SoundEvents.ENTITY_EXPERIENCE_ORB_PICKUP, SoundCategory.BLOCKS, 0.6f, 1.3f);
			} else {
				stack.set(ModComponents.GRIND_PROGRESS, progress);
				player.sendMessage(Text.translatable("msg.swordsmith.grind_progress", progress, Heat.GRIND_USES), true);
			}
			world.playSound(null, pos, SoundEvents.BLOCK_GRINDSTONE_USE, SoundCategory.BLOCKS, 0.6f,
					0.9f + world.getRandom().nextFloat() * 0.2f);
			if (world instanceof ServerWorld serverWorld) {
				serverWorld.spawnParticles(ParticleTypes.CRIT,
						pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5, 5, 0.2, 0.1, 0.2, 0.1);
			}
			return ItemActionResult.SUCCESS;
		}

		if (stack.isOf(ModItems.SHARP_BLADE)) {
			if (!world.isClient) {
				player.sendMessage(Text.translatable("msg.swordsmith.grind_already_sharp"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		if (stack.getItem() instanceof HeatableItem) {
			if (!world.isClient) {
				player.sendMessage(Text.translatable("msg.swordsmith.grind_wrong"), true);
			}
			return ItemActionResult.SUCCESS;
		}

		return ItemActionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
	}
}
