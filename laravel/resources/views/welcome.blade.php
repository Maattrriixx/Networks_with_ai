@foreach ($icon as $i )
 
        <img src="{{ asset($i->icon) }}" alt="{{ $i->name }}">
        

@endforeach