<?php

namespace Database\Seeders;

use App\Models\Icon;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class IconSeeder extends Seeder
{
    /**
     * Run the database seeds.
     */
    public function run(): void
    {
          $icon = [
            [
                'name' => 'Router',
                'icon' => 'icon\router.png'
            ],
            [
                'name' => 'Server',
                'icon' => 'icon\server.png'
            ],
            [
                'name' => 'Modem',
                'icon' => 'icon\modem.png'
            ],
            [
                'name' => 'Pc',
                'icon' => 'icon\pc.png'
            ],
            [
                'name' => 'Laptop',
                'icon' => 'icon\laptop.png'
            ],
            [
                'name' => 'Tv',
                'icon' => 'icon\tv.png'
            ],
            [
                'name' => 'Home_Router',
                'icon' => 'icon\homerouter.png'
            ],
            [
                'name' => 'Fire_wall',
                'icon' => 'icon\firewall.png'
            ],
            [
                'name' => 'Printer',
                'icon' => 'icon\printer.png'
            ],
            [
                'name' => 'Repeater',
                'icon' => 'icon\repeater.png'
            ],
            [
                'name' => 'Switch',
                'icon' => 'icon\switch.png'
            ],
        ];
        foreach($icon as $item){
            Icon::create($item);
        }
    }
}
