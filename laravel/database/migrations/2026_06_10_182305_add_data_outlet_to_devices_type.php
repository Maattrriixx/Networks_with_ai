<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        DB::statement("ALTER TABLE devices MODIFY COLUMN type ENUM(
        'access_point',
        'camera',
        'switch',
        'router',
        'firewall',
        'patch_panel',
        'ups',
        'server',
        'data_outlet'
    ) NOT NULL");
    }

    public function down(): void
    {
        DB::statement("ALTER TABLE devices MODIFY COLUMN type ENUM(
        'access_point',
        'camera',
        'switch',
        'router',
        'firewall',
        'patch_panel',
        'ups',
        'server'
    ) NOT NULL");
    }
};
