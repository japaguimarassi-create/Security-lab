package br.com.japaguimarassi.stevebo;

import java.util.List;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityCreature;
import net.minecraft.entity.EntityLivingBase;
import net.minecraft.entity.SharedMonsterAttributes;
import net.minecraft.entity.monster.EntityMob;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.util.DamageSource;
import net.minecraft.world.World;
import net.minecraft.entity.ai.EntityAISwimming;
import net.minecraft.entity.ai.EntityAIWander;
import net.minecraft.entity.ai.EntityAIWatchClosest;
import net.minecraft.entity.ai.EntityAILookIdle;

public class EntityStevebo extends EntityCreature {
    private EntityPlayer followTarget;
    private EntityPlayer duelTarget;
    private EntityPlayer protectTarget;
    private int pathCooldown;
    private int attackCooldown;

    public EntityStevebo(World world) {
        super(world);
        setSize(0.6F, 1.8F);
        setCustomNameTag("Stevebô");
        setAlwaysRenderNameTag(true);
        tasks.addTask(0, new EntityAISwimming(this));
        tasks.addTask(5, new EntityAIWander(this, 0.8D));
        tasks.addTask(6, new EntityAIWatchClosest(this, EntityPlayer.class, 12.0F));
        tasks.addTask(7, new EntityAILookIdle(this));
    }

    @Override
    protected void applyEntityAttributes() {
        super.applyEntityAttributes();
        getEntityAttribute(SharedMonsterAttributes.maxHealth).setBaseValue(40.0D);
        getEntityAttribute(SharedMonsterAttributes.movementSpeed).setBaseValue(0.32D);
    }

    @Override
    public void onLivingUpdate() {
        super.onLivingUpdate();
        if (attackCooldown > 0) attackCooldown--;
        if (pathCooldown > 0) pathCooldown--;

        if (duelTarget != null && !duelTarget.isDead && duelTarget.worldObj == worldObj) {
            engage(duelTarget, 1.18D, true);
            return;
        }

        if (protectTarget != null && !protectTarget.isDead && protectTarget.worldObj == worldObj) {
            EntityMob hostile = findHostileNear(protectTarget);
            if (hostile != null) {
                engage(hostile, 1.15D, true);
            } else {
                follow(protectTarget);
            }
            return;
        }

        if (followTarget != null && !followTarget.isDead && followTarget.worldObj == worldObj) {
            engage(followTarget, 1.05D, false);
        } else if (followTarget != null) {
            followTarget = null;
        }
    }

    private void engage(Entity target, double speed, boolean attack) {
        getLookHelper().setLookPositionWithEntity(target, 20.0F, 20.0F);
        double distance = getDistanceSqToEntity(target);
        if (distance > (attack ? 3.2D : 9.0D) && pathCooldown == 0) {
            getNavigator().tryMoveToEntityLiving(target, speed);
            pathCooldown = 8;
        }
        if (attack && distance < 6.25D && attackCooldown == 0 && target instanceof EntityLivingBase) {
            ((EntityLivingBase) target).attackEntityFrom(DamageSource.causeMobDamage(this), 5.0F);
            attackCooldown = 20;
        }
    }

    private void follow(EntityPlayer player) {
        followTarget = player;
        duelTarget = null;
        protectTarget = null;
        if (getDistanceSqToEntity(player) > 9.0D && pathCooldown == 0) {
            getNavigator().tryMoveToEntityLiving(player, 1.05D);
            pathCooldown = 8;
        }
    }

    private EntityMob findHostileNear(EntityPlayer player) {
        List<EntityMob> mobs = worldObj.getEntitiesWithinAABB(EntityMob.class, player.boundingBox.expand(14.0D, 7.0D, 14.0D));
        EntityMob closest = null;
        double bestDistance = Double.MAX_VALUE;
        for (EntityMob mob : mobs) {
            if (mob == this || mob.isDead) continue;
            double distance = getDistanceSqToEntity(mob);
            if (distance < bestDistance) {
                bestDistance = distance;
                closest = mob;
            }
        }
        return closest;
    }

    public void commandFollow(EntityPlayer player) {
        followTarget = player;
        duelTarget = null;
        protectTarget = null;
        getNavigator().clearPathEntity();
    }

    public void commandStop() {
        followTarget = null;
        duelTarget = null;
        protectTarget = null;
        getNavigator().clearPathEntity();
    }

    public void commandProtect(EntityPlayer player) {
        followTarget = null;
        duelTarget = null;
        protectTarget = player;
        getNavigator().clearPathEntity();
    }

    public void commandDuel(EntityPlayer player) {
        followTarget = null;
        protectTarget = null;
        duelTarget = player;
        getNavigator().clearPathEntity();
    }

    @Override
    public boolean canDespawn() {
        return false;
    }
}