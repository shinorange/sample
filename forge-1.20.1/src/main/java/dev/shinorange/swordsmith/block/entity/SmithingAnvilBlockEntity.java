package dev.shinorange.swordsmith.block.entity;

import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.registry.ModRegistry;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.game.ClientGamePacketListener;
import net.minecraft.network.protocol.game.ClientboundBlockEntityDataPacket;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

/**
 * Holds the workpiece lying on the anvil face (rendered in-world), the strike
 * counter, and the hilt-assembly state. The workpiece keeps its heat NBT and
 * cools naturally while it sits here.
 */
public class SmithingAnvilBlockEntity extends BlockEntity {
	private ItemStack workpiece = ItemStack.EMPTY;
	private int strikes;
	private int peenStrikes;
	private boolean guard;
	private boolean grip;
	private boolean pommel;

	public SmithingAnvilBlockEntity(BlockPos pos, BlockState state) {
		super(ModRegistry.SMITHING_ANVIL_BE.get(), pos, state);
	}

	public ItemStack getWorkpiece() {
		return workpiece;
	}

	public void setWorkpiece(ItemStack stack) {
		workpiece = stack;
		strikes = 0;
		setChangedAndSync();
	}

	public void markWorkpieceChanged() {
		setChangedAndSync();
	}

	public int getStrikes() {
		return strikes;
	}

	public void addStrike() {
		strikes++;
		setChanged();
	}

	public void resetStrikes() {
		strikes = 0;
		setChanged();
	}

	public boolean hasGuard() {
		return guard;
	}

	public boolean hasGrip() {
		return grip;
	}

	public boolean hasPommel() {
		return pommel;
	}

	public void setGuard() {
		guard = true;
		setChangedAndSync();
	}

	public void setGrip() {
		grip = true;
		setChangedAndSync();
	}

	public void setPommel() {
		pommel = true;
		setChangedAndSync();
	}

	public boolean isAwaitingPeen() {
		return workpiece.is(ModRegistry.SHARP_BLADE.get()) && guard && grip && pommel;
	}

	public int getPeenStrikes() {
		return peenStrikes;
	}

	public void addPeenStrike() {
		peenStrikes++;
		setChanged();
	}

	public String nextAssemblyStepKey() {
		if (!guard) {
			return "msg.swordsmith.attach_need_guard";
		}
		if (!grip) {
			return "msg.swordsmith.attach_need_grip";
		}
		if (!pommel) {
			return "msg.swordsmith.attach_need_pommel";
		}
		return "msg.swordsmith.peen_hint";
	}

	/** The peening is done: the parts become one sword, as good as its making. */
	public void finishSword() {
		float quality = Quality.finalQuality(workpiece);
		ItemStack sword = new ItemStack(ModRegistry.FORGED_STEEL_SWORD.get());
		Quality.applyToSword(sword, quality);
		workpiece = sword;
		guard = false;
		grip = false;
		pommel = false;
		strikes = 0;
		peenStrikes = 0;
		setChangedAndSync();
	}

	/** Clears the anvil, returning the workpiece and any not-yet-peened hilt parts. */
	public List<ItemStack> removeEverything() {
		List<ItemStack> stacks = new ArrayList<>();
		if (!workpiece.isEmpty()) {
			stacks.add(workpiece);
		}
		if (guard) {
			stacks.add(new ItemStack(ModRegistry.SWORD_GUARD.get()));
		}
		if (grip) {
			stacks.add(new ItemStack(ModRegistry.SWORD_GRIP.get()));
		}
		if (pommel) {
			stacks.add(new ItemStack(ModRegistry.SWORD_POMMEL.get()));
		}
		workpiece = ItemStack.EMPTY;
		strikes = 0;
		peenStrikes = 0;
		guard = false;
		grip = false;
		pommel = false;
		setChangedAndSync();
		return stacks;
	}

	private void setChangedAndSync() {
		setChanged();
		if (level != null) {
			level.sendBlockUpdated(worldPosition, getBlockState(), getBlockState(), Block.UPDATE_CLIENTS);
		}
	}

	@Override
	protected void saveAdditional(CompoundTag tag) {
		super.saveAdditional(tag);
		if (!workpiece.isEmpty()) {
			tag.put("Workpiece", workpiece.save(new CompoundTag()));
		}
		tag.putInt("Strikes", strikes);
		tag.putInt("PeenStrikes", peenStrikes);
		tag.putBoolean("Guard", guard);
		tag.putBoolean("Grip", grip);
		tag.putBoolean("Pommel", pommel);
	}

	@Override
	public void load(CompoundTag tag) {
		super.load(tag);
		workpiece = tag.contains("Workpiece") ? ItemStack.of(tag.getCompound("Workpiece")) : ItemStack.EMPTY;
		strikes = tag.getInt("Strikes");
		peenStrikes = tag.getInt("PeenStrikes");
		guard = tag.getBoolean("Guard");
		grip = tag.getBoolean("Grip");
		pommel = tag.getBoolean("Pommel");
	}

	@Override
	public Packet<ClientGamePacketListener> getUpdatePacket() {
		return ClientboundBlockEntityDataPacket.create(this);
	}

	@Override
	public CompoundTag getUpdateTag() {
		return saveWithoutMetadata();
	}
}
