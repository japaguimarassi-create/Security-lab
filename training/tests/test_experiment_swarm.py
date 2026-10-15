import unittest

from training.experiment_swarm import config_for_trial, shard_trial_count, trial_ids_for_shard


class ExperimentSwarmTests(unittest.TestCase):
    def test_million_trials_are_partitioned_without_overlap(self):
        total = 1_000_000
        shards = 16
        all_ids = []
        for shard_id in range(shards):
            count = shard_trial_count(total, shard_id, shards)
            ids = list(trial_ids_for_shard(total, shard_id, shards, limit=8))
            self.assertEqual(count, 62500)
            self.assertTrue(all(value % shards == shard_id for value in ids))
            all_ids.extend(ids)
        self.assertEqual(len(all_ids), 128)
        self.assertEqual(len(set(all_ids)), 128)

    def test_shard_count_handles_small_and_unbalanced_queues(self):
        self.assertEqual(shard_trial_count(2, 0, 4), 1)
        self.assertEqual(shard_trial_count(2, 1, 4), 1)
        self.assertEqual(shard_trial_count(2, 2, 4), 0)
        self.assertEqual(shard_trial_count(11, 3, 4), 2)

    def test_batches_advance_without_overlapping_or_skipping_trial_ids(self):
        total = 23
        shard_count = 4
        batch_size = 2
        executed = []
        for shard_id in range(shard_count):
            for batch_index in range(10):
                executed.extend(trial_ids_for_shard(
                    total,
                    shard_id,
                    shard_count,
                    limit=batch_size,
                    batch_index=batch_index,
                ))
        self.assertEqual(sorted(executed), list(range(total)))
        self.assertEqual(len(executed), len(set(executed)))

    def test_configurations_are_deterministic_and_seeds_are_unique(self):
        self.assertEqual(config_for_trial(90), config_for_trial(90))
        seeds = {config_for_trial(index)["seed"] for index in range(200)}
        self.assertEqual(len(seeds), 200)
        for index in range(100):
            config = config_for_trial(index)
            self.assertIn(config["learning_rate"], [1e-4, 2e-4, 3e-4, 5e-4])
            self.assertIn(config["dropout"], [0.0, 0.05, 0.1, 0.15, 0.2])
            self.assertIn(config["max_seq_len"], [64, 128])


if __name__ == "__main__":
    unittest.main()
