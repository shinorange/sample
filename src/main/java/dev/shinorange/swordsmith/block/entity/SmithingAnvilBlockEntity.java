package dev.shinorange.swordsmith.block.entity;

import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.QualityData;
import dev.shinorange.swordsmith.registry.ModBlockEntities;
import dev.shinorange.swordsmith.registry.ModComponents;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.component.DataComponentTypes;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.nbt.NbtCompound;
import net.minecraft.network.listener.ClientPlayPacketListener;
import net.minecraft.network.packet.Packet;
import net.minecraft.network.packet.s2c.play.BlockEntityUpdateS2CPacket;
import net.minecraft.registry.RegistryWrapper;
import net.minecraft.util.math.BlockPos;

/**
 * Holds the workpiece lying on the anvil face (rendered in-world), the strike
 * counter for the current forging step, and the hilt-assembly state for the
 * final step. The workpiece keeps its heat component, so it cools naturally
 * while it sits here.
 */
public class SmithingAnvilBlockEntity extends BlockEntity {
	private ItemStack workpiece = ItemStack.EMPTY;
	private int strikes;
	private int peenStrikes;
	private boolean guard;
	private boolean grip;
	private boolean pommel;

	public SmithingAnvilBlockEntity(BlockPos pos, BlockState state) {
		super(ModBlockEntities.SMITHING_ANVIL, pos, state);
	}

	public ItemStack getWorkpiece() {
		return workpiece;
	}

	public void setWorkpiece(ItemStack stack) {
		workpiece = stack;
		strikes = 0;
		markDirtyAndSync();
	}

	/** The workpiece stack was mutated in place (heat re-stamped); persist and resync. */
	public void markWorkpieceChanged() {
		markDirtyAndSync();
	}

	public int getStrikes() {
		return strikes;
	}

	public void addStrike() {
		strikes++;
		markDirty();
	}

	public void resetStrikes() {
		strikes = 0;
		markDirty();
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
		markDirtyAndSync();
	}

	public void setGrip() {
		grip = true;
		markDirtyAndSync();
	}

	public void setPommel() {
		pommel = true;
		markDirtyAndSync();
	}

	public boolean isAwaitingPeen() {
		return workpiece.isOf(ModItems.SHARP_BLADE) && guard && grip && pommel;
	}

	public int getPeenStrikes() {
		return peenStrikes;
	}

	public void addPeenStrike() {
		peenStrikes++;
		markDirty();
	}

	/** Translation key describing what the assembly needs next. */
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
		QualityData data = workpiece.get(ModComponents.QUALITY);
		float quality = data == null ? 0.7f : data.finalQuality();
		ItemStack sword = new ItemStack(ModItems.FORGED_STEEL_SWORD);
		sword.set(ModComponents.SWORD_QUALITY, quality);
		sword.set(DataComponentTypes.ATTRIBUTE_MODIFIERS, Quality.swordAttributes(quality));
		workpiece = sword;
		guard = false;
		grip = false;
		pommel = false;
		strikes = 0;
		peenStrikes = 0;
		markDirtyAndSync();
	}

	/** Clears the anvil, returning the workpiece and any not-yet-peened hilt parts. */
	public List<ItemStack> removeEverything() {
		List<ItemStack> stacks = new ArrayList<>();
		if (!workpiece.isEmpty()) {
			stacks.add(workpiece);
		}
		if (guard) {
			stacks.add(new ItemStack(ModItems.SWORD_GUARD));
		}
		if (grip) {
			stacks.add(new ItemStack(ModItems.SWORD_GRIP));
		}
		if (pommel) {
			stacks.add(new ItemStack(ModItems.SWORD_POMMEL));
		}
		workpiece = ItemStack.EMPTY;
		strikes = 0;
		peenStrikes = 0;
		guard = false;
		grip = false;
		pommel = false;
		markDirtyAndSync();
		return stacks;
	}

	private void markDirtyAndSync() {
		markDirty();
		if (world != null) {
			world.updateListeners(pos, getCachedState(), getCachedState(), Block.NOTIFY_LISTENERS);
		}
	}

	@Override
	public void writeNbt(NbtCompound nbt, RegistryWrapper.WrapperLookup registryLookup) {
		super.writeNbt(nbt, registryLookup);
		if (!workpiece.isEmpty()) {
			nbt.put("Workpiece", workpiece.encode(registryLookup));
		}
		nbt.putInt("Strikes", strikes);
		nbt.putInt("PeenStrikes", peenStrikes);
		nbt.putBoolean("Guard", guard);
		nbt.putBoolean("Grip", grip);
		nbt.putBoolean("Pommel", pommel);
	}

	@Override
	public void readNbt(NbtCompound nbt, RegistryWrapper.WrapperLookup registryLookup) {
		super.readNbt(nbt, registryLookup);
		workpiece = nbt.contains("Workpiece")
				? ItemStack.fromNbt(registryLookup, nbt.getCompound("Workpiece")).orElse(ItemStack.EMPTY)
				: ItemStack.EMPTY;
		strikes = nbt.getInt("Strikes");
		peenStrikes = nbt.getInt("PeenStrikes");
		guard = nbt.getBoolean("Guard");
		grip = nbt.getBoolean("Grip");
		pommel = nbt.getBoolean("Pommel");
	}

	@Override
	public Packet<ClientPlayPacketListener> toUpdatePacket() {
		return BlockEntityUpdateS2CPacket.create(this);
	}

	@Override
	public NbtCompound toInitialChunkDataNbt(RegistryWrapper.WrapperLookup registryLookup) {
		return createNbt(registryLookup);
	}
}
