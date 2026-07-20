package dev.shinorange.swordsmith.block;

import com.mojang.serialization.MapCodec;
import dev.shinorange.swordsmith.block.entity.SmithingAnvilBlockEntity;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.QualityData;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModComponents;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.block.Block;
import net.minecraft.block.BlockRenderType;
import net.minecraft.block.BlockState;
import net.minecraft.block.BlockWithEntity;
import net.minecraft.block.ShapeContext;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.entity.EquipmentSlot;
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
import net.minecraft.util.ActionResult;
import net.minecraft.util.BlockMirror;
import net.minecraft.util.BlockRotation;
import net.minecraft.util.Hand;
import net.minecraft.util.ItemActionResult;
import net.minecraft.util.ItemScatterer;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.util.shape.VoxelShape;
import net.minecraft.util.shape.VoxelShapes;
import net.minecraft.world.BlockView;
import net.minecraft.world.World;

/**
 * The smith's anvil. Lay a glowing workpiece on it and strike it with the
 * smithing hammer while it is at forging heat (720 C+). It also hosts the
 * final cold assembly: sharpened blade + guard + grip + pommel, peened
 * together with a few last hammer taps.
 */
public class SmithingAnvilBlock extends BlockWithEntity {
	public static final MapCodec<SmithingAnvilBlock> CODEC = createCodec(SmithingAnvilBlock::new);
	public static final DirectionProperty FACING = Properties.HORIZONTAL_FACING;

	private static final VoxelShape BASE = Block.createCuboidShape(2, 0, 2, 14, 4, 14);
	private static final VoxelShape X_STEM = Block.createCuboidShape(4, 4, 6, 12, 10, 10);
	private static final VoxelShape X_FACE = Block.createCuboidShape(0, 10, 3, 16, 16, 13);
	private static final VoxelShape Z_STEM = Block.createCuboidShape(6, 4, 4, 10, 10, 12);
	private static final VoxelShape Z_FACE = Block.createCuboidShape(3, 10, 0, 13, 16, 16);
	private static final VoxelShape X_SHAPE = VoxelShapes.union(BASE, X_STEM, X_FACE);
	private static final VoxelShape Z_SHAPE = VoxelShapes.union(BASE, Z_STEM, Z_FACE);

	public SmithingAnvilBlock(Settings settings) {
		super(settings);
		this.setDefaultState(this.getDefaultState().with(FACING, Direction.NORTH));
	}

	@Override
	protected MapCodec<? extends BlockWithEntity> getCodec() {
		return CODEC;
	}

	@Override
	protected void appendProperties(StateManager.Builder<Block, BlockState> builder) {
		builder.add(FACING);
	}

	@Override
	public BlockState getPlacementState(ItemPlacementContext ctx) {
		return this.getDefaultState().with(FACING, ctx.getHorizontalPlayerFacing().rotateYClockwise());
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
		return state.get(FACING).getAxis() == Direction.Axis.X ? X_SHAPE : Z_SHAPE;
	}

	@Override
	protected BlockRenderType getRenderType(BlockState state) {
		return BlockRenderType.MODEL;
	}

	@Override
	public BlockEntity createBlockEntity(BlockPos pos, BlockState state) {
		return new SmithingAnvilBlockEntity(pos, state);
	}

	@Override
	protected ItemActionResult onUseWithItem(ItemStack stack, BlockState state, World world, BlockPos pos, PlayerEntity player, Hand hand, BlockHitResult hit) {
		if (!(world.getBlockEntity(pos) instanceof SmithingAnvilBlockEntity anvil)) {
			return ItemActionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
		}

		if (stack.isOf(ModItems.SMITHING_HAMMER)) {
			if (world instanceof ServerWorld serverWorld) {
				strike(serverWorld, pos, player, stack, hand, anvil);
			}
			return ItemActionResult.SUCCESS;
		}

		if (stack.isOf(ModItems.SWORD_GUARD) || stack.isOf(ModItems.SWORD_GRIP) || stack.isOf(ModItems.SWORD_POMMEL)) {
			if (world instanceof ServerWorld serverWorld) {
				attach(serverWorld, pos, player, stack, anvil);
			}
			return ItemActionResult.SUCCESS;
		}

		if (Smithing.isHeatable(stack) && anvil.getWorkpiece().isEmpty()) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			ItemStack one = stack.copyWithCount(1);
			if (!player.isCreative()) {
				stack.decrement(1);
			}
			anvil.setWorkpiece(one);
			world.playSound(null, pos, SoundEvents.BLOCK_ANVIL_PLACE, SoundCategory.BLOCKS, 0.4f, 1.4f);
			return ItemActionResult.SUCCESS;
		}

		if (stack.isOf(ModItems.SMITHING_TONGS)) {
			if (world.isClient) {
				return ItemActionResult.SUCCESS;
			}
			takeEverything(world, pos, player, anvil);
			return ItemActionResult.SUCCESS;
		}

		return ItemActionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
	}

	@Override
	protected ActionResult onUse(BlockState state, World world, BlockPos pos, PlayerEntity player, BlockHitResult hit) {
		if (!(world.getBlockEntity(pos) instanceof SmithingAnvilBlockEntity anvil)) {
			return ActionResult.PASS;
		}
		if (world.isClient) {
			return ActionResult.SUCCESS;
		}
		takeEverything(world, pos, player, anvil);
		return ActionResult.SUCCESS;
	}

	private void takeEverything(World world, BlockPos pos, PlayerEntity player, SmithingAnvilBlockEntity anvil) {
		if (anvil.getWorkpiece().isEmpty()) {
			player.sendMessage(Text.translatable("msg.swordsmith.anvil_empty"), true);
			return;
		}
		for (ItemStack stack : anvil.removeEverything()) {
			player.getInventory().offerOrDrop(stack);
		}
		world.playSound(null, pos, SoundEvents.ENTITY_ITEM_FRAME_REMOVE_ITEM, SoundCategory.BLOCKS, 0.9f, 0.9f);
	}

	private void strike(ServerWorld world, BlockPos pos, PlayerEntity player, ItemStack hammer, Hand hand, SmithingAnvilBlockEntity anvil) {
		ItemStack workpiece = anvil.getWorkpiece();
		if (workpiece.isEmpty()) {
			player.sendMessage(Text.translatable("msg.swordsmith.anvil_empty"), true);
			return;
		}

		// Final cold assembly: peen the pommel over the tang.
		if (anvil.isAwaitingPeen()) {
			anvil.addPeenStrike();
			hammer.damage(1, player, hand == Hand.MAIN_HAND ? EquipmentSlot.MAINHAND : EquipmentSlot.OFFHAND);
			world.playSound(null, pos, SoundEvents.BLOCK_ANVIL_USE, SoundCategory.BLOCKS, 0.8f, 1.4f);
			spawnSparks(world, pos, 3, 0);
			if (anvil.getPeenStrikes() >= Heat.PEEN_STRIKES) {
				anvil.finishSword();
				player.sendMessage(Text.translatable("msg.swordsmith.sword_finished"), true);
				world.playSound(null, pos, SoundEvents.ENTITY_PLAYER_LEVELUP, SoundCategory.BLOCKS, 0.6f, 1.0f);
			} else {
				player.sendMessage(Text.translatable("msg.swordsmith.peen_ready",
						Heat.PEEN_STRIKES - anvil.getPeenStrikes()), true);
			}
			return;
		}

		// A sharpened blade wants its hilt furniture before any more hammering.
		if (workpiece.isOf(ModItems.SHARP_BLADE)) {
			player.sendMessage(Text.translatable(anvil.nextAssemblyStepKey()), true);
			return;
		}

		Smithing.Forging step = Smithing.forgingOf(workpiece.getItem());
		if (step == null) {
			player.sendMessage(Text.translatable("msg.swordsmith.not_forgeable"), true);
			return;
		}

		float temp = Heat.current(world, workpiece);
		if (temp < Heat.FORGING_MIN) {
			player.sendMessage(Text.translatable("msg.swordsmith.too_cold"), true);
			world.playSound(null, pos, SoundEvents.BLOCK_ANVIL_HIT, SoundCategory.BLOCKS, 0.5f, 0.6f);
			return;
		}

		// A strike in the bright orange-yellow band is craftsman's work.
		float score = Quality.strikeScore(temp);
		boolean perfect = score >= 1.0f;
		QualityData qualityData = workpiece.getOrDefault(ModComponents.QUALITY, QualityData.EMPTY);
		workpiece.set(ModComponents.QUALITY, qualityData.addStrike(score));

		anvil.addStrike();
		Heat.set(world, workpiece, temp - Heat.STRIKE_COOLING);
		anvil.markWorkpieceChanged();
		hammer.damage(1, player, hand == Hand.MAIN_HAND ? EquipmentSlot.MAINHAND : EquipmentSlot.OFFHAND);
		world.playSound(null, pos, SoundEvents.BLOCK_ANVIL_USE, SoundCategory.BLOCKS, 0.7f,
				(perfect ? 1.05f : 0.9f) + world.getRandom().nextFloat() * 0.2f);
		spawnSparks(world, pos, perfect ? 14 : 8, perfect ? 3 : 2);

		if (anvil.getStrikes() >= step.strikes()) {
			ItemStack next = new ItemStack(step.output());
			Quality.carry(workpiece, next);
			Heat.set(world, next, Math.max(Heat.AMBIENT, temp - Heat.STRIKE_COOLING));
			anvil.setWorkpiece(next);
			anvil.resetStrikes();
			player.sendMessage(Text.translatable("msg.swordsmith.stage_complete", next.getName()), true);
			world.playSound(null, pos, SoundEvents.ENTITY_EXPERIENCE_ORB_PICKUP, SoundCategory.BLOCKS, 0.6f, 1.1f);
		} else {
			player.sendMessage(Text.translatable(
					perfect ? "msg.swordsmith.forging_progress_perfect" : "msg.swordsmith.forging_progress",
					anvil.getStrikes(), step.strikes()), true);
		}
	}

	private void attach(ServerWorld world, BlockPos pos, PlayerEntity player, ItemStack stack, SmithingAnvilBlockEntity anvil) {
		ItemStack workpiece = anvil.getWorkpiece();
		if (!workpiece.isOf(ModItems.SHARP_BLADE)) {
			player.sendMessage(Text.translatable("msg.swordsmith.need_sharp_blade"), true);
			return;
		}
		if (Heat.current(world, workpiece) > Heat.COLD_WORK_MAX) {
			player.sendMessage(Text.translatable("msg.swordsmith.attach_hot"), true);
			return;
		}

		boolean attached = false;
		if (stack.isOf(ModItems.SWORD_GUARD) && !anvil.hasGuard()) {
			anvil.setGuard();
			attached = true;
		} else if (stack.isOf(ModItems.SWORD_GRIP) && anvil.hasGuard() && !anvil.hasGrip()) {
			anvil.setGrip();
			attached = true;
		} else if (stack.isOf(ModItems.SWORD_POMMEL) && anvil.hasGrip() && !anvil.hasPommel()) {
			anvil.setPommel();
			attached = true;
		}

		if (attached) {
			if (!player.isCreative()) {
				stack.decrement(1);
			}
			world.playSound(null, pos, SoundEvents.ENTITY_ITEM_FRAME_ADD_ITEM, SoundCategory.BLOCKS, 1.0f, 1.1f);
		}
		player.sendMessage(Text.translatable(anvil.nextAssemblyStepKey()), true);
	}

	private void spawnSparks(ServerWorld world, BlockPos pos, int crit, int lava) {
		double x = pos.getX() + 0.5;
		double y = pos.getY() + 1.1;
		double z = pos.getZ() + 0.5;
		if (crit > 0) {
			world.spawnParticles(ParticleTypes.CRIT, x, y, z, crit, 0.25, 0.1, 0.25, 0.15);
		}
		if (lava > 0) {
			world.spawnParticles(ParticleTypes.LAVA, x, y, z, lava, 0.15, 0.05, 0.15, 0.0);
		}
	}

	@Override
	protected void onStateReplaced(BlockState state, World world, BlockPos pos, BlockState newState, boolean moved) {
		if (!state.isOf(newState.getBlock()) && world.getBlockEntity(pos) instanceof SmithingAnvilBlockEntity anvil) {
			for (ItemStack stack : anvil.removeEverything()) {
				ItemScatterer.spawn(world, pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5, stack);
			}
		}
		super.onStateReplaced(state, world, pos, newState, moved);
	}
}
